using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

[assembly: AssemblyTitle("Colin TTS Local")]
[assembly: AssemblyDescription("Windows launcher for Colin TTS Local voice studio")]
[assembly: AssemblyCompany("Colin TTS")]
[assembly: AssemblyProduct("Colin TTS Local")]
[assembly: AssemblyCopyright("Copyright © Colin TTS 2026")]
[assembly: AssemblyVersion("0.3.1.0")]
[assembly: AssemblyFileVersion("0.3.1.0")]

namespace ColinTTS.WindowsLauncher
{
    internal static class Program
    {
        private const string AppUserModelId = "ColinTTS.Local.Desktop";
        private const string ShortcutName = "Colin TTS Local.lnk";

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

        [STAThread]
        private static int Main(string[] args)
        {
            SetCurrentProcessExplicitAppUserModelID(AppUserModelId);
            string executablePath = Assembly.GetExecutingAssembly().Location;
            string root = Path.GetDirectoryName(executablePath) ?? Environment.CurrentDirectory;

            try
            {
                InstallShortcuts(root, executablePath);
            }
            catch (Exception error)
            {
                Debug.WriteLine("Shortcut installation failed: " + error);
            }

            if (HasArgument(args, "--install-shortcuts"))
            {
                return 0;
            }

            bool qtMode = HasArgument(args, "--qt");
            string batch = FindBatch(root, qtMode);
            if (batch == null)
            {
                ShowError("Could not find Start-ColinTTS.bat, run_qt.bat, or colinttslocal.bat beside ColinTTS.exe.");
                return 2;
            }

            string forwardedArguments = BuildForwardedArguments(args, qtMode);
            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = batch;
            startInfo.WorkingDirectory = root;
            startInfo.Arguments = forwardedArguments;
            startInfo.UseShellExecute = true;
            Process.Start(startInfo);
            return 0;
        }

        private static string FindBatch(string root, bool qtMode)
        {
            if (qtMode)
            {
                string qtBatch = Path.Combine(root, "run_qt.bat");
                return File.Exists(qtBatch) ? qtBatch : null;
            }

            string portableBatch = Path.Combine(root, "colinttslocal.bat");
            if (File.Exists(portableBatch))
            {
                return portableBatch;
            }

            string sourceBatch = Path.Combine(root, "Start-ColinTTS.bat");
            return File.Exists(sourceBatch) ? sourceBatch : null;
        }

        private static string BuildForwardedArguments(string[] args, bool qtMode)
        {
            string result = "";
            foreach (string argument in args)
            {
                if (String.Equals(argument, "--qt", StringComparison.OrdinalIgnoreCase) ||
                    String.Equals(argument, "--install-shortcuts", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }
                string value = String.Equals(argument, "--web", StringComparison.OrdinalIgnoreCase)
                    ? "-Web"
                    : argument;
                if (result.Length > 0)
                {
                    result += " ";
                }
                result += QuoteArgument(value);
            }
            return result;
        }

        private static string QuoteArgument(string value)
        {
            if (value.IndexOfAny(new char[] { ' ', '\t', '"' }) < 0)
            {
                return value;
            }
            return "\"" + value.Replace("\"", "\\\"") + "\"";
        }

        private static bool HasArgument(string[] args, string expected)
        {
            foreach (string argument in args)
            {
                if (String.Equals(argument, expected, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }

        private static void InstallShortcuts(string root, string executablePath)
        {
            string iconSource = FindIcon(root);
            if (iconSource == null)
            {
                throw new FileNotFoundException("Packaged Colin TTS icon was not found.");
            }

            string localAssets = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "ColinTTSLocal"
            );
            Directory.CreateDirectory(localAssets);
            string stableIcon = Path.Combine(localAssets, "colin_tts.ico");
            File.Copy(iconSource, stableIcon, true);

            string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            if (!String.IsNullOrWhiteSpace(desktop))
            {
                CreateShortcut(Path.Combine(desktop, ShortcutName), executablePath, root, stableIcon);
            }

            string startMenu = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
            if (!String.IsNullOrWhiteSpace(startMenu))
            {
                CreateShortcut(Path.Combine(startMenu, ShortcutName), executablePath, root, stableIcon);
            }
        }

        private static string FindIcon(string root)
        {
            string[] candidates = new string[]
            {
                Path.Combine(root, "src", "omni_tts_shared", "assets", "colin_tts.ico"),
                Path.Combine(root, "app", "src", "omni_tts_shared", "assets", "colin_tts.ico"),
                Path.Combine(root, "assets", "colin_tts.ico")
            };
            foreach (string candidate in candidates)
            {
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }
            return null;
        }

        private static void CreateShortcut(
            string shortcutPath,
            string targetPath,
            string workingDirectory,
            string iconPath)
        {
            IShellLinkW link = (IShellLinkW)new ShellLink();
            link.SetPath(targetPath);
            link.SetWorkingDirectory(workingDirectory);
            link.SetDescription("Open Colin TTS Local");
            link.SetIconLocation(iconPath, 0);
            link.SetShowCmd(1);

            IPropertyStore propertyStore = (IPropertyStore)link;
            PropertyKey appIdKey = new PropertyKey(
                new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
                5
            );
            using (PropVariant appId = PropVariant.FromString(AppUserModelId))
            {
                propertyStore.SetValue(ref appIdKey, ref appId.Value);
                propertyStore.Commit();
            }

            ((IPersistFile)link).Save(shortcutPath, true);
            Marshal.FinalReleaseComObject(link);
        }

        private static void ShowError(string message)
        {
            MessageBox(IntPtr.Zero, message, "Colin TTS Local", 0x10);
        }

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int MessageBox(IntPtr hwnd, string text, string caption, uint type);
    }

    [ComImport]
    [Guid("00021401-0000-0000-C000-000000000046")]
    internal class ShellLink
    {
    }

    [ComImport]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    [Guid("000214F9-0000-0000-C000-000000000046")]
    internal interface IShellLinkW
    {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] System.Text.StringBuilder path, int pathMax, IntPtr findData, uint flags);
        void GetIDList(out IntPtr idList);
        void SetIDList(IntPtr idList);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] System.Text.StringBuilder name, int nameMax);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] System.Text.StringBuilder directory, int directoryMax);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string directory);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] System.Text.StringBuilder arguments, int argumentsMax);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string arguments);
        void GetHotkey(out short hotkey);
        void SetHotkey(short hotkey);
        void GetShowCmd(out int showCommand);
        void SetShowCmd(int showCommand);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] System.Text.StringBuilder iconPath, int iconPathMax, out int iconIndex);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string iconPath, int iconIndex);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
        void Resolve(IntPtr hwnd, uint flags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string path);
    }

    [ComImport]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    [Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
    internal interface IPropertyStore
    {
        void GetCount(out uint count);
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariantNative value);
        void SetValue(ref PropertyKey key, ref PropVariantNative value);
        void Commit();
    }

    [ComImport]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    [Guid("0000010b-0000-0000-C000-000000000046")]
    internal interface IPersistFile
    {
        void GetClassID(out Guid classId);
        [PreserveSig]
        int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string fileName, uint mode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string fileName, bool remember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string fileName);
        void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string fileName);
    }

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    internal struct PropertyKey
    {
        public Guid FormatId;
        public uint PropertyId;

        public PropertyKey(Guid formatId, uint propertyId)
        {
            FormatId = formatId;
            PropertyId = propertyId;
        }
    }

    [StructLayout(LayoutKind.Explicit)]
    internal struct PropVariantNative
    {
        [FieldOffset(0)] public ushort ValueType;
        [FieldOffset(8)] public IntPtr PointerValue;
    }

    internal sealed class PropVariant : IDisposable
    {
        public PropVariantNative Value;

        private PropVariant()
        {
        }

        public static PropVariant FromString(string value)
        {
            PropVariant result = new PropVariant();
            result.Value.ValueType = 31; // VT_LPWSTR
            result.Value.PointerValue = Marshal.StringToCoTaskMemUni(value);
            return result;
        }

        public void Dispose()
        {
            if (Value.PointerValue != IntPtr.Zero)
            {
                Marshal.FreeCoTaskMem(Value.PointerValue);
                Value.PointerValue = IntPtr.Zero;
            }
        }
    }
}
