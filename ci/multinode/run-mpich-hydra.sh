#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${MANA_TEST_HOSTFILE:-}" ]]; then
    echo "SKIP: MANA_TEST_HOSTFILE is not set"
    exit 0
fi

: "${MANA_HOME:?Set MANA_HOME to the built MANA tree}"
: "${MANA_TEST_MPICH_HOME:?Set MANA_TEST_MPICH_HOME}"

REMOTE_USER="${MANA_TEST_REMOTE_USER:-${USER}}"
RANKS="${MANA_TEST_RANKS:-2}"
COORD_PORT="${MANA_TEST_COORD_PORT:-7780}"
WORK_BASE="${MANA_TEST_WORKDIR:-/tmp}"
TIMEOUT_SECONDS="${MANA_TEST_TIMEOUT:-300}"
SSH_BIN="${MANA_TEST_SSH:-ssh}"
SCP_BIN="${MANA_TEST_SCP:-scp}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Remote command strings below use simple absolute paths. Reject shell syntax.
for path in "$MANA_HOME" "$MANA_TEST_MPICH_HOME" "$WORK_BASE"; do
    [[ "$path" =~ ^/[a-zA-Z0-9_./-]+$ ]] || {
        echo "ERROR: use absolute paths without spaces or shell metacharacters: $path" >&2
        exit 1
    }
done
for value in "$RANKS" "$TIMEOUT_SECONDS"; do
    [[ "$value" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: ranks and timeout must be positive integers" >&2; exit 1; }
done
[[ "$COORD_PORT" =~ ^[0-9]+$ && ${#COORD_PORT} -le 5 ]] &&
    ((10#$COORD_PORT <= 65535)) || { echo "ERROR: invalid coordinator port" >&2; exit 1; }
[[ "$REMOTE_USER" =~ ^[a-zA-Z0-9_.-]+$ ]] || { echo "ERROR: invalid remote user" >&2; exit 1; }
mkdir -p "$WORK_BASE"
WORKDIR="$(mktemp -d "$WORK_BASE/mana-multinode.XXXXXXXX")"
TEST_HOME="$WORKDIR/home"
echo "Evidence directory: $WORKDIR"

APP="$WORKDIR/mpi_counter"
HOSTFILE="$WORKDIR/hosts.txt"
CKPTDIR="$WORKDIR/checkpoints"
TEST_TMPDIR="$WORKDIR/tmp"
LOGDIR="$WORKDIR/logs"
COORD_LOG="$WORKDIR/coordinator.log"
LAUNCH_LOG="$WORKDIR/launch.log"
RESTART_LOG="$WORKDIR/restart.log"
STATUS_FILE="$TEST_HOME/.mana.rc"

MPICC="$MANA_TEST_MPICH_HOME/bin/mpicc"
MPIEXEC="$MANA_TEST_MPICH_HOME/bin/mpiexec"
DMTCP_COORD="$MANA_HOME/bin/dmtcp_coordinator"
DMTCP_COMMAND="$MANA_HOME/bin/dmtcp_command"
MANA_LAUNCH="$MANA_HOME/bin/mana_launch"
MANA_RESTART="$MANA_HOME/bin/mana_restart"

for executable in \
    "$MPICC" "$MPIEXEC" "$DMTCP_COORD" "$DMTCP_COMMAND" \
    "$MANA_LAUNCH" "$MANA_RESTART" "$MANA_HOME/bin/lower-half"
do
    [[ -x "$executable" ]] || {
        echo "ERROR: missing executable: $executable" >&2
        exit 1
    }
done

[[ -r "$MANA_TEST_HOSTFILE" ]] || {
    echo "ERROR: cannot read hostfile: $MANA_TEST_HOSTFILE" >&2
    exit 1
}

mapfile -t NODES < <(
    sed \
      -e 's/[[:space:]]*#.*$//' \
      -e 's/\r$//' \
      -e 's/^[[:space:]]*//' \
      -e 's/[[:space:]]*$//' \
      "$MANA_TEST_HOSTFILE" |
    awk 'NF {host=$1; sub(/:.*/, "", host); if (!seen[host]++) print host}'
)

[[ "${#NODES[@]}" -ge 2 && "$RANKS" -ge 2 ]] || {
    echo "ERROR: multi-node validation requires at least two hosts and two ranks" >&2
    exit 1
}

for host in "${NODES[@]}"; do
    [[ "$host" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || {
        echo "ERROR: unsupported hostname: $host" >&2
        exit 1
    }
done

SSH_LAUNCHER="$WORKDIR/ssh-launcher"
printf '#!/usr/bin/env bash\nexec %q -n -o BatchMode=yes -o ConnectTimeout=10 -l %q "$@"\n' \
    "$SSH_BIN" "$REMOTE_USER" > "$SSH_LAUNCHER"
chmod 700 "$SSH_LAUNCHER"

remote_target() {
    local host="$1"
    if [[ -n "$REMOTE_USER" ]]; then
        printf '%s@%s' "$REMOTE_USER" "$host"
    else
        printf '%s' "$host"
    fi
}

remote() {
    local host="$1"
    shift
    timeout --signal=TERM --kill-after=5s "$TIMEOUT_SECONDS" \
      "$SSH_BIN" -n -o BatchMode=yes -o ConnectTimeout=10 "$(remote_target "$host")" "$@"
}

copy_to() {
    local source="$1"
    local host="$2"
    local destination="$3"
    # On shared storage, source and destination can be the same file.
    local digest
    digest="$(sha256sum "$source" | cut -d ' ' -f1)"
    if remote "$host" "test -f '$destination' && test \"\$(sha256sum '$destination' | cut -d ' ' -f1)\" = '$digest'"; then
        return 0
    fi
    timeout --signal=TERM --kill-after=5s "$TIMEOUT_SECONDS" \
      "$SCP_BIN" -q -o BatchMode=yes -o ConnectTimeout=10 "$source" "$(remote_target "$host"):$destination" </dev/null
}

coord_host=""
coord_port=""

read_status_file() {
    coord_host="$(awk '/^Host:/ {print $2; exit}' "$STATUS_FILE")"
    coord_port="$(awk '/^Port:/ {print $2; exit}' "$STATUS_FILE")"
    [[ -n "$coord_host" && -n "$coord_port" ]] || {
        echo "ERROR: invalid coordinator status file: $STATUS_FILE" >&2
        return 1
    }
}

command_to_coordinator() {
    read_status_file
    timeout --signal=TERM --kill-after=5s 10s "$DMTCP_COMMAND" \
      --coord-host "$coord_host" \
      --coord-port "$coord_port" \
      "$@"
}

launch_pid=""
restart_pid=""
stop_launcher() {
    local pid="$1"
    [[ -n "$pid" ]] || return 0
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        for ((attempt=0; attempt<10; ++attempt)); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
        done
        kill -KILL "$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
}

cleanup() {
    local result="$?"
    trap - EXIT INT TERM
    set +e
    if [[ -s "$STATUS_FILE" ]]; then
        command_to_coordinator --kill >/dev/null 2>&1
        command_to_coordinator --quit >/dev/null 2>&1
    fi
    # Hydra owns and tears down its remote proxies; never scan arbitrary PIDs.
    stop_launcher "$launch_pid"
    stop_launcher "$restart_pid"
    echo "Evidence retained in: $WORKDIR"
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

status_text() {
    command_to_coordinator --status 2>/dev/null || true
}

list_text() {
    command_to_coordinator --list 2>/dev/null || true
}

wait_for_peers() {
    local expected="$1"
    local limit="$2"
    local peers=0
    for ((second=0; second<limit; ++second)); do
        peers="$(status_text | awk -F= '/NUM_PEERS=/{gsub(/[[:space:]]/, "", $2); print $2; exit}')"
        peers="${peers:-0}"
        if [[ "$peers" -eq "$expected" ]]; then
            return 0
        fi
        sleep 1
    done
    echo "ERROR: expected $expected peers; observed $peers" >&2
    status_text >&2
    list_text >&2
    return 1
}

verify_images() {
    local host rank output
    local -A found=()
    for host in "${NODES[@]}"; do
        output="$(remote "$host" "find '$CKPTDIR' -type f -name '*.tmp' -print")" || return 1
        [[ -z "$output" ]] || return 1
        for ((rank=0; rank<RANKS; ++rank)); do
            output="$(remote "$host" "if test -d '$CKPTDIR/ckpt_rank_$rank'; then find '$CKPTDIR/ckpt_rank_$rank' -type f -name '*.dmtcp' -size +0c -print; fi")" || return 1
            [[ -z "$output" ]] || found[$rank]=1
        done
    done
    [[ "${#found[@]}" -eq "$RANKS" ]]
}

wait_for_images() {
    local limit="$1"
    for ((second=0; second<limit; ++second)); do
        if verify_images; then
            return 0
        fi
        sleep 1
    done
    echo "ERROR: complete checkpoint images were not found" >&2
    return 1
}

mkdir -p "$WORKDIR" "$TEST_HOME" "$CKPTDIR" "$TEST_TMPDIR" "$LOGDIR"

# Preserve the rank layout supplied by the user, while stripping comments and CRLF.
sed \
  -e 's/[[:space:]]*#.*$//' \
  -e 's/\r$//' \
  -e 's/^[[:space:]]*//' \
  -e 's/[[:space:]]*$//' \
  -e '/^$/d' \
  "$MANA_TEST_HOSTFILE" > "$HOSTFILE"

for host in "${NODES[@]}"; do
    echo "Checking $host..."
    remote "$host" "
      set -eu
      test -x '$MANA_HOME/bin/mana_launch'
      test -x '$MANA_HOME/bin/mana_restart'
      test -x '$MANA_HOME/bin/lower-half'
      test -x '$MANA_TEST_MPICH_HOME/bin/hydra_pmi_proxy'
      mkdir -p '$WORKDIR' '$TEST_HOME' '$CKPTDIR' '$TEST_TMPDIR' '$LOGDIR'
      rm -f '$LOGDIR'/rank_*.log '$STATUS_FILE'
    "
    copy_to "$HOSTFILE" "$host" "$HOSTFILE"
done

"$MPICC" -O2 -g -Wall -Wextra -Wpedantic \
  "$SCRIPT_DIR/mpi_counter.c" -o "$APP"

for host in "${NODES[@]}"; do
    copy_to "$APP" "$host" "$APP"
    remote "$host" "chmod 755 '$APP'"
done

MPI_BASE=(
    env -u SLURM_JOB_ID -u SLURM_JOBID "$MPIEXEC"
    -launcher ssh
    -launcher-exec "$SSH_LAUNCHER"
    -wdir "$WORKDIR"
    -f "$HOSTFILE"
    -n "$RANKS"
    -genv HOME "$TEST_HOME"
    -genv MANA_HOME "$MANA_HOME"
    -genv MPICH_HOME "$MANA_TEST_MPICH_HOME"
    -genv PATH "$MANA_HOME/bin:$MANA_TEST_MPICH_HOME/bin:$PATH"
    -genv LD_LIBRARY_PATH "$MANA_HOME/lib:$MANA_HOME/lib/dmtcp:$MANA_TEST_MPICH_HOME/lib:${LD_LIBRARY_PATH:-}"
    -genv HYDRA_LAUNCHER ssh
    -genv HYDRA_ENV all
)

echo "[1/7] Native MPICH/Hydra smoke"
timeout --signal=TERM --kill-after=20s "$TIMEOUT_SECONDS" "${MPI_BASE[@]}" "$APP" 5 "$LOGDIR"

start_coordinator() {
    rm -f "$STATUS_FILE"
    "$DMTCP_COORD" \
        --port "$COORD_PORT" \
        --interval 0 \
        --ckptdir "$CKPTDIR" \
        --coord-logfile "$COORD_LOG" \
        --daemon \
        --status-file "$STATUS_FILE"
    for ((second=0; second<30; ++second)); do
        if [[ -s "$STATUS_FILE" ]] && read_status_file 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    echo "ERROR: coordinator did not create complete status in $STATUS_FILE" >&2
    return 1
}

echo "[2/7] Start persistent coordinator"
start_coordinator

for host in "${NODES[@]}"; do
    copy_to "$STATUS_FILE" "$host" "$STATUS_FILE"
    remote "$host" "
      host=\$(awk '/^Host:/ {print \$2; exit}' '$STATUS_FILE')
      port=\$(awk '/^Port:/ {print \$2; exit}' '$STATUS_FILE')
      '$DMTCP_COMMAND' --coord-host \"\$host\" --coord-port \"\$port\" --status >/dev/null
    "
done

echo "[3/7] Finite MANA smoke"
timeout --signal=TERM --kill-after=20s "$TIMEOUT_SECONDS" "${MPI_BASE[@]}" \
    "$MANA_LAUNCH" \
    --ckptdir "$CKPTDIR" \
    --tmpdir "$TEST_TMPDIR" \
    "$APP" 5 "$LOGDIR"

# The finite test disconnects, but the underlying coordinator remains persistent.
command_to_coordinator --status >/dev/null

# Start a fresh coordinator and clear finite-test logs/checkpoints.
command_to_coordinator --quit >/dev/null 2>&1 || true
rm -rf "$CKPTDIR" "$TEST_TMPDIR" "$LOGDIR"
mkdir -p "$CKPTDIR" "$TEST_TMPDIR" "$LOGDIR"
for host in "${NODES[@]}"; do
    remote "$host" "rm -rf '$CKPTDIR' '$TEST_TMPDIR' '$LOGDIR'; mkdir -p '$CKPTDIR' '$TEST_TMPDIR' '$LOGDIR'"
done
start_coordinator
for host in "${NODES[@]}"; do copy_to "$STATUS_FILE" "$host" "$STATUS_FILE"; done

echo "[4/7] Long-running MANA launch"
nohup "${MPI_BASE[@]}" \
    "$MANA_LAUNCH" \
    --ckptdir "$CKPTDIR" \
    --tmpdir "$TEST_TMPDIR" \
    "$APP" 0 "$LOGDIR" \
    > "$LAUNCH_LOG" 2>&1 &
launch_pid="$!"
wait_for_peers "$RANKS" "$TIMEOUT_SECONDS"
sleep 10

echo "[5/7] Blocking checkpoint"
timeout --signal=TERM --kill-after=20s "$TIMEOUT_SECONDS" \
    "$DMTCP_COMMAND" \
    --coord-host "$coord_host" \
    --coord-port "$coord_port" \
    --bcheckpoint
wait_for_images "$TIMEOUT_SECONDS"
# Let the original computation advance beyond the saved state before killing it.
sleep 5

pre_max="$(awk 'match($0,/iteration=[0-9]+/){v=substr($0,RSTART+10,RLENGTH-10)+0;if(!s||v>m)m=v;s=1}END{if(s)print m}' "$LAUNCH_LOG")"
[[ -n "$pre_max" ]] || {
    echo "ERROR: no pre-checkpoint iteration found" >&2
    exit 1
}

echo "[6/7] Kill and restart"
command_to_coordinator --kill >/dev/null 2>&1 || true
sleep 3
stop_launcher "$launch_pid"
launch_pid=""
command_to_coordinator --quit >/dev/null 2>&1 || true

start_coordinator
for host in "${NODES[@]}"; do copy_to "$STATUS_FILE" "$host" "$STATUS_FILE"; done

MPI_RESTART=(
    env -u SLURM_JOB_ID -u SLURM_JOBID "$MPIEXEC"
    -launcher ssh
    -launcher-exec "$SSH_LAUNCHER"
    -wdir "$WORKDIR"
    -f "$HOSTFILE"
    -n "$RANKS"
    -genv HOME "$TEST_HOME"
    -genv MANA_HOME "$MANA_HOME"
    -genv MPICH_HOME "$MANA_TEST_MPICH_HOME"
    -genv PATH "$MANA_HOME/bin:$MANA_TEST_MPICH_HOME/bin:$PATH"
    -genv LD_LIBRARY_PATH "$MANA_HOME/lib:$MANA_HOME/lib/dmtcp:$MANA_TEST_MPICH_HOME/lib:${LD_LIBRARY_PATH:-}"
    -genv DMTCP_LOG_LEVEL trace
    -genv HYDRA_LAUNCHER ssh
    -genv HYDRA_ENV all
)

nohup "${MPI_RESTART[@]}" \
    "$MANA_RESTART" \
    --verbose \
    --ckptdir "$CKPTDIR" \
    --tmpdir "$TEST_TMPDIR" \
    --restartdir "$CKPTDIR" \
    > "$RESTART_LOG" 2>&1 &
restart_pid="$!"
wait_for_peers "$RANKS" "$TIMEOUT_SECONDS"
verified=0
for ((second=0; second<TIMEOUT_SECONDS; ++second)); do
    if python3 "$SCRIPT_DIR/verify.py" "$LAUNCH_LOG" "$RESTART_LOG" "$RANKS" \
        > "$WORKDIR/verification.log" 2>&1; then
        verified=1
        break
    fi
    kill -0 "$restart_pid" 2>/dev/null || break
    sleep 1
done
if [[ "$verified" -ne 1 ]]; then
    cat "$WORKDIR/verification.log" >&2
    exit 1
fi

command_to_coordinator --kill >/dev/null 2>&1 || true
stop_launcher "$restart_pid"
restart_pid=""

echo "[7/7] Verify rollback, collective result, and progress"
python3 "$SCRIPT_DIR/verify.py" "$LAUNCH_LOG" "$RESTART_LOG" "$RANKS"

echo "PASS: multi-node MPICH/Hydra checkpoint-restart validation"
echo "Evidence directory: $WORKDIR"
