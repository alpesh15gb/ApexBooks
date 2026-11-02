using ApexBooks_Windows.Services;
using Microsoft.UI.Xaml.Controls;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;
public sealed partial class MainPage
{
    private StackPanel CapabilityNotice()
    {
        var panel=Stack(6);var hint=Text(Api.Capabilities.Hint,12);panel.Children.Add(hint);
        if(Api.Capabilities.Retryable){var epoch=workspaceGeneration;var view=generation;Button? retry=null;retry=AsyncButton("Retry feature check",async()=>{
            if(!Api.SignedIn||epoch!=workspaceGeneration||view!=generation)return;
            hint.Text="Checking available features…";await Api.RetryCapabilities();
            if(!Api.SignedIn||epoch!=workspaceGeneration||view!=generation)return;
            hint.Text=Api.Capabilities.Retryable?Api.Capabilities.Hint:Api.Capabilities.Valid?"Feature check complete. Reopen this view to use the available features; your current entries are unchanged.":Api.Capabilities.Hint;
            retry!.Visibility=Api.Capabilities.Retryable?Microsoft.UI.Xaml.Visibility.Visible:Microsoft.UI.Xaml.Visibility.Collapsed;
        },Error);panel.Children.Add(retry);}return panel;
    }
    private bool Supports(string feature)=>Api.Capabilities.Supports(feature);
    private void RequireFeature(string feature){if(!Supports(feature))throw new Exception(Api.Capabilities.Hint);}
    private Button FeatureButton(string label,string feature,Func<Task> action,bool primary=false)
    {
        var button=AsyncButton(label,action,Error,primary);button.IsEnabled=Supports(feature);
        if(!button.IsEnabled)ToolTipService.SetToolTip(button,Api.Capabilities.Hint);return button;
    }
}
