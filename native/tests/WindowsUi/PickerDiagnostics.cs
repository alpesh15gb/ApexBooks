using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Nodes;
using System.Windows.Automation;

// Failure-only metadata for synthetic UI tests. Never used to select or invoke a picker.
static class PickerDiagnostics
{
    static bool Matching(string title)=>title is "Open" or "Save As" or "Save as";
    static string Handle(nint value)=>"0x"+value.ToString("X");
    static JsonObject Native(nint hwnd){
        Api.GetWindowThreadProcessId(hwnd,out var pid);
        return new(){["hwnd"]=Handle(hwnd),["pid"]=pid,["visible"]=Api.IsWindowVisible(hwnd),["enabled"]=Api.IsWindowEnabled(hwnd)};
    }
    static JsonObject Chain(nint candidate,nint app){
        var rows=new JsonArray();var seen=new HashSet<nint>();var current=candidate;var stop="depth_limit";
        for(var depth=0;depth<32;depth++){
            if(current==0){stop="zero";break;}
            if(!seen.Add(current)){stop="cycle";break;}
            rows.Add(Native(current));
            if(current==app&&app!=0){stop="app_reached";break;}
            current=Api.GetWindow(current,4);
        }
        return new(){["nodes"]=rows,["stop"]=stop};
    }
    public static void Write(string directory,Process? process,AutomationElement? appWindow){
        var root=new JsonObject();nint appHwnd=0;
        try{
            root["launched_pid"]=process?.Id;
            if(process is not null&&!process.HasExited)root["process_main_hwnd"]=Handle(process.MainWindowHandle);
            if(appWindow is not null){var info=appWindow.Current;appHwnd=(nint)info.NativeWindowHandle;root["app_uia"]=new JsonObject{["hwnd"]=Handle(appHwnd),["pid"]=info.ProcessId,["enabled"]=info.IsEnabled,["offscreen"]=info.IsOffscreen};root["app_native"]=Native(appHwnd);}
        }catch(Exception error){root["app_error"]=error.GetType().Name;}
        var uia=new JsonArray();var native=new JsonArray();root["matching_uia_windows"]=uia;root["matching_native_windows"]=native;
        try{
            // No Window-type filter: capture whether that filter caused discovery failure.
            var candidates=AutomationElement.RootElement.FindAll(TreeScope.Children,Condition.TrueCondition);
            for(var index=0;index<Math.Min(candidates.Count,512)&&uia.Count<16;index++){
                try{var info=candidates[index].Current;if(!Matching(info.Name))continue;var hwnd=(nint)info.NativeWindowHandle;
                    uia.Add(new JsonObject{["title"]=info.Name,["type"]=info.ControlType.ProgrammaticName,["hwnd"]=Handle(hwnd),["pid"]=info.ProcessId,["enabled"]=info.IsEnabled,["offscreen"]=info.IsOffscreen,["native"]=Native(hwnd),["owner_chain"]=Chain(hwnd,appHwnd)});
                }catch(ElementNotAvailableException){/* A disappearing window is not a reason to expand scope. */}
            }
            root["uia_top_level_count"]=candidates.Count;
        }catch(Exception error){root["uia_error"]=error.GetType().Name;}
        try{
            var examined=0;
            Api.EnumWindows((hwnd,_)=>{
                if(++examined>2048||native.Count>=16)return false;
                try{var title=new StringBuilder(128);Api.GetWindowText(hwnd,title,title.Capacity);if(!Matching(title.ToString()))return true;
                    var row=Native(hwnd);row["title"]=title.ToString();row["owner_chain"]=Chain(hwnd,appHwnd);native.Add(row);
                }catch(Exception error){root["native_candidate_error"]=error.GetType().Name;}
                return true;
            },0);
            root["native_examined_count"]=examined;
        }catch(Exception error){root["native_error"]=error.GetType().Name;}
        File.WriteAllText(Path.Combine(directory,"picker-diagnostics.json"),root.ToJsonString());
        Console.WriteLine($"PICKER_DIAGNOSTICS matching UIA={uia.Count}, native={native.Count}; bounded owner metadata saved to artifact.");
    }
    static class Api
    {
        internal delegate bool Callback(nint hwnd,nint state);
        [DllImport("user32.dll",ExactSpelling=true)]internal static extern bool EnumWindows(Callback callback,nint state);
        [DllImport("user32.dll",CharSet=CharSet.Unicode)]internal static extern int GetWindowText(nint hwnd,StringBuilder text,int count);
        [DllImport("user32.dll",ExactSpelling=true)]internal static extern nint GetWindow(nint hwnd,uint command);
        [DllImport("user32.dll",ExactSpelling=true)]internal static extern uint GetWindowThreadProcessId(nint hwnd,out uint pid);
        [DllImport("user32.dll",ExactSpelling=true)]internal static extern bool IsWindowVisible(nint hwnd);
        [DllImport("user32.dll",ExactSpelling=true)]internal static extern bool IsWindowEnabled(nint hwnd);
    }
}
