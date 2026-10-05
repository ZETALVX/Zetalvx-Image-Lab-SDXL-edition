# Modified for Zetalvx 0.1.0.20 native entry/packaging; Apache-2.0 license and attribution retained in LICENSE and NOTICE.
"""Ensure a local child cannot outlive its owning app (Linux only)."""
import ctypes,os,signal,sys
def main():
    if sys.platform.startswith('linux'):
        parent=int(sys.argv[1]);ctypes.CDLL(None).prctl(1,signal.SIGTERM)
        if os.getppid()!=parent:sys.exit(1)
    os.execv(sys.argv[2],sys.argv[2:])

if __name__ == "__main__":
    main()
