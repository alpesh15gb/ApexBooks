using Microsoft.UI.Xaml;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace ApexBooks_Windows;

/// <summary>
/// The application window. This hosts a Frame that displays pages. Add your
/// UI and logic to MainPage.xaml / MainPage.xaml.cs instead of here so you
/// can use Page features such as navigation events and the Loaded lifecycle.
/// </summary>
public sealed partial class MainWindow : Window
{
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern uint GetDpiForWindow(nint window);

    public MainWindow()
    {
        InitializeComponent();
        Closed+=(_,_)=>Application.Current.Exit();
        var display=Microsoft.UI.Windowing.DisplayArea.GetFromWindowId(AppWindow.Id,Microsoft.UI.Windowing.DisplayAreaFallback.Primary);
        var area=display.WorkArea;
        // AppWindow coordinates are physical pixels; use a logical desktop size
        // so a high-DPI display does not launch a cramped mobile-width workspace.
        var scale=Math.Max(1d,GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(this))/96d);
        var width=Math.Min((int)Math.Round(1280*scale),Math.Max(320,area.Width-64));var height=Math.Min((int)Math.Round(900*scale),Math.Max(400,area.Height-64));
        AppWindow.MoveAndResize(new Windows.Graphics.RectInt32(area.X+(area.Width-width)/2,area.Y+(area.Height-height)/2,width,height));

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);

        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory,"Assets","AppIcon.ico"));

        // Navigate the root frame to the main page on startup.
        RootFrame.Navigate(typeof(MainPage));
    }
}
