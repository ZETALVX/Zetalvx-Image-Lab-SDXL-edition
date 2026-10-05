// Zetalvx Image Lab - SDXL Edition 1.0.15, Apache-2.0. No shell commands; links are never traversed.
// Managed traversal, Windows extended paths; no registry or system settings changed.
using System;
using System.IO;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
namespace ZetalvxUninstall {
    public sealed class TreeRemoval {
        public readonly List<string> Errors = new List<string>();
        public DateTime DeadlineUtc = DateTime.UtcNow.AddMinutes(10);
        public Action<long,string> Progress;
        private long pending;
        private string lastPath = "";
        private readonly Stopwatch timer = Stopwatch.StartNew();
        private static readonly bool Windows = Environment.OSVersion.Platform == PlatformID.Win32NT;
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
        private static extern bool DeleteFileW(string name);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
        private static extern bool RemoveDirectoryW(string name);
        public static string NativePath(string path) {
            string full=Path.GetFullPath(path);
            if (!Windows || full.StartsWith(@"\\?\",StringComparison.Ordinal)) return full;
            if (full.StartsWith(@"\\",StringComparison.Ordinal)) return @"\\?\UNC\"+full.Substring(2);
            return @"\\?\"+full;
        }
        private void Notify(bool force) {
            if (force || timer.ElapsedMilliseconds >= 1000) {
                if (Progress != null) Progress(pending,lastPath);
                pending=0; timer.Restart();
            }
        }
        private void RemoveLeaf(string p, bool directory) {
            if (Windows) {
                bool ok=directory ? RemoveDirectoryW(p) : DeleteFileW(p);
                if (!ok) {
                    int error=Marshal.GetLastWin32Error();
                    if (error==2 || error==3) return;
                    throw new System.ComponentModel.Win32Exception(error);
                }
            } else if (directory) Directory.Delete(p,false);
            else File.Delete(p);
            pending++;
        }
        private void Walk(string p) {
            if (DateTime.UtcNow >= DeadlineUtc) throw new TimeoutException("Removal exceeded its time limit. Last path: "+p);
            lastPath=p; Notify(false);
            FileAttributes attrs;
            try { attrs=File.GetAttributes(p); }
            catch (FileNotFoundException) { return; }
            catch (DirectoryNotFoundException) { return; }
            bool dir=(attrs & FileAttributes.Directory)!=0;
            // Includes directory junctions and symlinks: unlink only, don't visit target.
            if ((attrs & FileAttributes.ReparsePoint)!=0) { RemoveLeaf(p,dir); return; }
            if (dir) {
                foreach (string child in Directory.EnumerateFileSystemEntries(p)) {
                    try { Walk(child); }
                    catch (TimeoutException) { throw; }
                    catch (Exception ex) { if (Errors.Count<16) Errors.Add(child+": "+ex.Message); }
                }
            }
            if ((attrs & FileAttributes.ReadOnly)!=0) File.SetAttributes(p,attrs & ~FileAttributes.ReadOnly);
            RemoveLeaf(p,dir);
        }
        public void Remove(string path) {
            // Windows PowerShell's .NET Framework: opt in inside this process only.
            AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling",false);
            AppContext.SetSwitch("Switch.System.IO.BlockLongPaths",false);
            try { Walk(NativePath(path)); }
            catch (Exception ex) { if (Errors.Count<16) Errors.Add(path+": "+ex.Message); }
            finally { Notify(true); }
        }
    }
}
