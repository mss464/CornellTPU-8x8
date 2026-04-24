import paramiko
import os
import sys

def run_test():
    host = "132.236.59.68"
    user = "xilinx"
    pw = "xilinx"
    
    remote_root = "/home/xilinx/minitpu_deploy"
    bitstream_name = "minitpu.bit"
    hwh_name = "minitpu.hwh"
    local_bitstream = f"/home/mss464/minitpu/tpu/ultra96-v2/output/artifacts/{bitstream_name}"
    local_hwh = f"/home/mss464/minitpu/tpu/ultra96-v2/output/artifacts/{hwh_name}"
    local_test_script = "/home/mss464/minitpu/tpu/board_tests/test_mem_system.py"
    local_driver = "/home/mss464/minitpu/tpu/pynq_host_driver.py"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, username=user, password=pw, timeout=10)
        print("Connected to board.", flush=True)
        
        # Setup board directory structure
        stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {remote_root}/board_tests {remote_root}/runtime")
        stdout.channel.recv_exit_status() # Wait for command to finish
        print("Created remote directories.", flush=True)
        
        sftp = ssh.open_sftp()
        print("Opened SFTP session.", flush=True)
        print("Uploading test files and bitstream...", flush=True)
        sftp.put(local_test_script, f"{remote_root}/board_tests/test_mem_system.py")
        sftp.put(local_driver, f"{remote_root}/runtime/pynq_host.py")
        sftp.put(local_bitstream, f"{remote_root}/{bitstream_name}")
        sftp.put(local_hwh, f"{remote_root}/{hwh_name}")
        sftp.close()
        
        print(f"Executing test suite on board (with sudo and --program) using bitstream: {bitstream_name}", flush=True)
        # Added --program to ensure Overlay is initialized/loaded correctly
        cmd = f"cd {remote_root} && echo {pw} | sudo -S python3 board_tests/test_mem_system.py --verbose --bitstream {bitstream_name} --program"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        for line in stdout:
            print(line.strip(), flush=True)
        for line in stderr:
            err_line = line.strip()
            if "[sudo]" not in err_line:
                print(f"ERR: {err_line}", file=sys.stderr, flush=True)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    run_test()
