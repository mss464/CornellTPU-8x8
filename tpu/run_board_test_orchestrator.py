import paramiko
import os
import sys

def run_test():
    host = "132.236.59.75"
    user = "xilinx"
    pw = "xilinx"
    
    remote_root = "/home/xilinx/minitpu_deploy"
    bitstream_path = "/home/xilinx/tpu_deploy/mem_bd.bit" 
    local_test_script = "/home/mss464/minitpu/tpu/board_tests/test_mem_system.py"
    local_driver = "/home/mss464/minitpu/tpu/pynq_host_driver.py"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, username=user, password=pw, timeout=10)
        
        # Setup board directory structure
        ssh.exec_command(f"mkdir -p {remote_root}/board_tests {remote_root}/runtime")
        
        sftp = ssh.open_sftp()
        print("Uploading test files...")
        sftp.put(local_test_script, f"{remote_root}/board_tests/test_mem_system.py")
        sftp.put(local_driver, f"{remote_root}/runtime/pynq_host.py")
        sftp.close()
        
        print(f"Executing test suite on board (with sudo and --program) using bitstream: {bitstream_path}")
        # Added --program to ensure Overlay is initialized/loaded correctly
        cmd = f"cd {remote_root} && echo {pw} | sudo -S python3 board_tests/test_mem_system.py --verbose --bitstream {bitstream_path} --program"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        for line in stdout:
            print(line.strip())
        for line in stderr:
            err_line = line.strip()
            if "[sudo]" not in err_line:
                print(f"ERR: {err_line}", file=sys.stderr)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    run_test()
