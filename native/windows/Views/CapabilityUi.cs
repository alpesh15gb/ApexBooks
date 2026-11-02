using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml.Controls;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private StackPanel CapabilityNotice()
    {
        var epoch=workspaceGeneration;var view=generation;var panel=Stack(6);var hint=Text(Api.Capabilities.Hint,12);panel.Children.Add(hint);Button? retry=null;
        bool Current()=>Api.SignedIn&&epoch==workspaceGeneration&&view==generation;
        void Updated(){if(!Current())return;hint.Text=Api.Capabilities.Valid?"Server feature check complete. Reopen an editor to use newly available options; current entries are unchanged."+(Api.Capabilities.HasCoreAdditions?"":" "+Api.Capabilities.Hint):Api.Capabilities.Hint;retry!.Visibility=Api.Capabilities.Retryable?Microsoft.UI.Xaml.Visibility.Visible:Microsoft.UI.Xaml.Visibility.Collapsed;}
        retry=AsyncButton("Retry feature check",async()=>{if(!Current())return;hint.Text="Checking available features…";await Api.RetryCapabilities();Updated();},Error);retry.Visibility=Api.Capabilities.Retryable?Microsoft.UI.Xaml.Visibility.Visible:Microsoft.UI.Xaml.Visibility.Collapsed;panel.Children.Add(retry);
        async Task Observe(){await Api.EnsureCapabilities();Updated();}
        if(Api.Capabilities.Pending)_=Observe();return panel;
    }
    private bool Supports(string feature)=>Api.Capabilities.Supports(feature);
    private void RequireFeature(string feature){if(!Supports(feature))throw new Exception(Api.Capabilities.Hint);}
    private Button FeatureButton(string label,string feature,Func<Task> action,bool primary=false)
    {
        var button=AsyncButton(label,action,Error,primary);button.IsEnabled=Supports(feature);
        if(!button.IsEnabled)ToolTipService.SetToolTip(button,Api.Capabilities.Hint);
        if(Api.Capabilities.Pending){var epoch=workspaceGeneration;var view=generation;async Task Observe(){await Api.EnsureCapabilities();if(Api.SignedIn&&epoch==workspaceGeneration&&view==generation){button.IsEnabled=Supports(feature);ToolTipService.SetToolTip(button,button.IsEnabled?null:Api.Capabilities.Hint);}}_=Observe();}return button;
    }
}
