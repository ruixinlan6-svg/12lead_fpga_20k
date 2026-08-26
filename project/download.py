import subprocess
import sys
import os

PROGRAMMER_PATH = r"D:\software\Gowin\Gowin_V1.9.12.03_x64\Programmer\bin\programmer_cli.exe"
FS_FILE = os.path.abspath(r"impl\pnr\project.fs")

def main():
    mode = "sram"
    if len(sys.argv) > 1 and sys.argv[1].lower() in ["flash", "spi", "rom"]:
        mode = "flash"

    if not os.path.exists(PROGRAMMER_PATH):
        print(f"Error: programmer_cli.exe not found at {PROGRAMMER_PATH}")
        sys.exit(1)

    if not os.path.exists(FS_FILE):
        print(f"Error: Bitstream file {FS_FILE} not found. Please build first!")
        sys.exit(1)

    # Mode 2 = SRAM Program (fast, volatile)
    # Mode 44 = sFlash Erase,Program (persistent SPI flash)
    run_code = "44" if mode == "flash" else "2"
    mode_name = "SPI Flash (Persistent)" if mode == "flash" else "SRAM (Direct Run)"

    cmd = [
        PROGRAMMER_PATH,
        "--device", "GW2AR-18C",
        "--run", run_code,
        "--fsFile", FS_FILE
    ]

    print(f"[*] Burning Bitstream to {mode_name}...")
    print(f"[*] Command: {' '.join(cmd)}")
    ret = subprocess.run(cmd)
    if ret.returncode == 0:
        print(f"[+] Successfully programmed FPGA ({mode_name})!")
    else:
        print(f"[-] Programming failed with return code {ret.returncode}")
        sys.exit(ret.returncode)

if __name__ == "__main__":
    main()
