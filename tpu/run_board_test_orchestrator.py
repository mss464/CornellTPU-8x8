import paramiko
import os
import socket
import sys
import time

def describe_artifact(path):
    st = os.stat(path)
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
    return f"{path} ({st.st_size} bytes, mtime={mtime})"

def get_env_float(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc

def run_test():
    host = os.environ.get("TPU_BOARD_HOST", "132.236.59.68")
    user = os.environ.get("TPU_BOARD_USER", "xilinx")
    pw = os.environ.get("TPU_BOARD_PASSWORD", "xilinx")
    ssh_timeout = get_env_float("TPU_SSH_TIMEOUT", 30.0)
    
    remote_root = "/home/xilinx/minitpu_deploy"
    bitstream_name = "mem_bd.bit"
    hwh_name = "mem_bd.hwh"
    tpu_root = os.path.dirname(os.path.abspath(__file__))
    artifact_dir = os.environ.get("TPU_ARTIFACT_DIR")
    if artifact_dir is None:
        for candidate in (
            os.path.join(tpu_root, "ultra96-v2", "output", "artifacts"),
            os.path.join(tpu_root, "build", "artifacts"),
        ):
            if (os.path.exists(os.path.join(candidate, bitstream_name)) and
                    os.path.exists(os.path.join(candidate, hwh_name))):
                artifact_dir = candidate
                break
    if artifact_dir is None:
        raise FileNotFoundError(f"Could not find {bitstream_name}/{hwh_name}")

    local_bitstream = os.path.join(artifact_dir, bitstream_name)
    local_hwh = os.path.join(artifact_dir, hwh_name)
    local_test_script = os.path.join(tpu_root, "board_tests", "test_mem_system.py")
    local_driver = os.path.join(tpu_root, "runtime", "pynq_host.py")

    for path in (local_bitstream, local_hwh, local_test_script, local_driver):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"Connecting to board at {user}@{host} (timeout={ssh_timeout:g}s)...", flush=True)
        ssh.connect(
            host,
            username=user,
            password=pw,
            timeout=ssh_timeout,
            banner_timeout=ssh_timeout,
            auth_timeout=ssh_timeout,
        )
        print("Connected to board.", flush=True)
        
        # Setup board directory structure
        stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {remote_root}/board_tests {remote_root}/runtime")
        stdout.channel.recv_exit_status() # Wait for command to finish
        print("Created remote directories.", flush=True)
        
        sftp = ssh.open_sftp()
        print("Opened SFTP session.", flush=True)
        print("Uploading test files and bitstream...", flush=True)
        print(f"Using artifacts from: {artifact_dir}", flush=True)
        print(f"Bitstream artifact: {describe_artifact(local_bitstream)}", flush=True)
        print(f"HWH artifact: {describe_artifact(local_hwh)}", flush=True)
        sftp.put(local_test_script, f"{remote_root}/board_tests/test_mem_system.py")
        sftp.put(local_driver, f"{remote_root}/runtime/pynq_host.py")
        sftp.put(local_bitstream, f"{remote_root}/{bitstream_name}")
        sftp.put(local_hwh, f"{remote_root}/{hwh_name}")
        sftp.close()
        
        print(f"Executing test suite on board (with sudo and --program) using bitstream: {bitstream_name}", flush=True)
        # Added --program to ensure Overlay is initialized/loaded correctly
        # Added --latency 1 for the Ultra96 board's observed BRAM behavior
        cmd = f"cd {remote_root} && echo {pw} | sudo -S python3 board_tests/test_mem_system.py --verbose --bitstream {bitstream_name} --program --latency 1"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        for line in stdout:
            print(line.strip(), flush=True)
        for line in stderr:
            err_line = line.strip()
            if "[sudo]" not in err_line:
                print(f"ERR: {err_line}", file=sys.stderr, flush=True)
            
    except (TimeoutError, socket.timeout) as e:
        print(f"Error: SSH connection to {user}@{host} timed out after {ssh_timeout:g}s: {e}")
        print("Check board power/network reachability, or set TPU_BOARD_HOST/TPU_SSH_TIMEOUT before rerunning.")
    except Exception as e:
        print(f"Error ({type(e).__name__}): {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    run_test()
