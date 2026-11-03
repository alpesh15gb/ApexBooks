using ApexBooks_Windows.Models;
using ApexBooks_Windows.Services;
using ApexBooks_Windows.Views;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net.Http;
using System.Text.Json.Nodes;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    private async Task EditDocument(string kind, JsonObject? previous = null, JsonObject? conversion = null,JsonObject? returnSource=null,JsonObject? draftSeed=null)
    {
        var cid = CompanyId; var stamp = generation;
        var editorSession=Api.SessionGeneration;var inlineOpen=false;InlineMasterSubmission? inlineCommand=null;
        var inlineAllowed=kind=="sales_invoice"&&previous is null&&conversion is null&&returnSource is null&&draftSeed is null&&CanWrite;
        if (conversion is not null) conversion = (await Api.Record(cid, conversion.Text("id"))).Object();
        if (stamp != generation) return;
        var source = previous ?? conversion ?? returnSource ?? draftSeed; var data = source?["data"].Object() ?? new();
        var regular = Company.Text("tax_mode") == "regular"; var purchase = kind is "purchase_bill" or "purchase_order" or "debit_note" or "expense";
        var panel = Stack(16); panel.Width = Math.Clamp(((App.Window.Content as FrameworkElement)?.ActualWidth ?? 1240) - 112, 420, 1320);
        panel.Children.Add(Text(Company.Text("name") + " · " + (regular ? "GST registered" : "GST not charged on sales"), 13));
        var info = new InfoBar { IsClosable = true };
        void LocalError(Exception e) { info.Severity = InfoBarSeverity.Error; info.Message = e.Message; info.IsOpen = true; }
        panel.Children.Add(info);if(!Api.Capabilities.HasCoreAdditions)panel.Children.Add(CapabilityNotice());
        var party = new AutoSuggestBox { Header = kind == "expense" ? "Supplier / expense description" : "Customer / supplier", Text = source.Text("name"), PlaceholderText = "Choose a party or enter a name" };
        var number = Input("Reference number", previous.Text("number"));number.PlaceholderText="Assigned on save";number.MaxLength=16;
        var date = new DateInput("Document date", previous.Text("date") is { Length: > 0 } d ? d : J.Today);
        var due = new DateInput("Due date · optional", data.Text("due_date"));
        var address = Input("Billing address", data.Text("party_address"), true); var gstin = Input("Party GSTIN", data.Text("party_gstin")); var phone = Input("Phone", data.Text("party_phone"));
        var shipping = Input("Shipping address", data.Text("shipping_address"), true);var lastShippingDefault="";
        var supplierState = Input("Supplier state code", data.Text("supplier_state") is { Length: > 0 } ss ? ss : data.Text("party_gstin").Length>=2 ? data.Text("party_gstin")[..2] : Company.Text("state_code"));
        var supply = Input("Place of supply · state code", data.Text("place_of_supply") is { Length: > 0 } ps ? ps : Company.Text("state_code"));
        var discount = Input("Document discount (%)", data.Text("document_discount_percent") is { Length: > 0 } disc ? disc : "0");
        var round = new CheckBox { Content = "Round total to nearest rupee", IsChecked = data.Flag("round_total") };
        var returnStock = new CheckBox { Content = "Return stock with this note", IsChecked = !data.ContainsKey("return_stock") || data.Flag("return_stock") };
        var method = Select("Paid through", [("cash", "Cash"), ("bank", "Bank / UPI / card")], data.Text("payment_account") is { Length: > 0 } pay ? pay : "cash");
        var bank = BankChoice(selected: data.Text("bank_account_id") is { Length: > 0 } bankId ? bankId : "default");
        var category = Input("Expense category", data.Text("category") is { Length: > 0 } cat ? cat : "General");
        var tender = Input("Cash tendered (₹)", data.Text("tender_amount"));
        var notes = Input("Notes", data.Text("notes"), true); var terms = Input("Terms and conditions", data.Text("terms"), true);
        notes.MaxLength=4000;terms.MaxLength=8000;gstin.MaxLength=15;phone.MaxLength=32;address.MaxLength=1000;shipping.MaxLength=1000;
        var linesPanel = Stack(12); var lines = new List<DocumentLine>(); var preview = Text("Enter items to calculate the total.", 16, true); preview.Foreground = Green;
        var creditInfo=new InfoBar{IsClosable=false};var checkCredit=Supports("party_credit_limits")&&WorkflowMasterValues.CreditProjectionApplies(kind,previous is not null);
        Button? termsSuggestion=null;TextBlock? termsHint=null;
        var fixedReview=new FixedDiscountReview();CheckBox? fixedReviewBox=null;
        var partyId = data.Text("party_id"); var appliedTo = returnSource?.Text("id")??data.Text("applied_to");
        var retryKey = Guid.NewGuid().ToString();var submission=new RetrySubmission(); CancellationTokenSource? previewRequest = null;var sourceLoading=false;

        JsonObject DocumentData()
        {
            var values = new JsonObject { ["lines"] = new JsonArray(lines.Select(line => (JsonNode)line.Data()).ToArray()), ["party_id"] = partyId, ["party_address"] = address.Text, ["party_gstin"] = gstin.Text.Trim().ToUpperInvariant(), ["party_phone"] = phone.Text, ["shipping_address"] = shipping.Text, ["place_of_supply"] = supply.Text.Trim(), ["supplier_state"] = supplierState.Text.Trim(), ["notes"] = notes.Text, ["terms"] = terms.Text, ["document_discount_percent"] = discount.Text.Trim().Length > 0 ? discount.Text.Trim() : "0", ["round_total"] = round.IsChecked == true, ["return_stock"] = returnStock.IsChecked == true, ["category"] = category.Text, ["payment_account"] = Value(method) };
            values["due_date"] = due.Value;
            if (Value(method) == "bank") values["bank_account_id"] = Value(bank);
            if (tender.Text.Length > 0) values["tender_amount"] = tender.Text;
            if (appliedTo.Length > 0) values["applied_to"] = appliedTo;
            if (previous is not null) values["version"] = data["version"].Copy() ?? JsonValue.Create(0);
            if (conversion is not null) values["source_document_id"] = conversion.Text("id");
            return values;
        }
        string FixedSignature()=>appliedTo+"|"+string.Join("|",lines.Select(line=>line.DiscountReviewIdentity+":"+line.DiscountReviewRevision+":"+line.Quantity.Text+":"+line.Data().Text("discount_amount")));
        bool NeedsFixedReview()=>FixedDiscountReview.Needed(kind is "credit_note" or "debit_note"&&appliedTo.Length>0,lines.Select(line=>line.Data()));
        void UpdateFixedReview(){if(fixedReviewBox is null)return;fixedReviewBox.Visibility=NeedsFixedReview()?Visibility.Visible:Visibility.Collapsed;if(fixedReviewBox.IsChecked==true&&!fixedReview.IsAcknowledged(FixedSignature()))fixedReviewBox.IsChecked=false;}
        JsonObject BodyValue() => new() { ["kind"] = kind, ["name"] = party.Text.Trim(), ["number"] = number.Text.Trim(), ["date"] = date.Value, ["data"] = DocumentData() };
        async Task Calculate()
        {
            UpdateFixedReview();
            if(termsSuggestion is not null)termsSuggestion.IsEnabled=partyId.Length>0&&!submission.Unresolved;if(termsHint is not null)termsHint.Text=partyId.Length>0?"Suggestions use the selected saved party’s terms; applying is always explicit.":"Choose a saved party to use payment terms, or set the due date manually for a freeform name.";
            previewRequest?.Cancel(); var request = new CancellationTokenSource(); previewRequest = request;creditInfo.IsOpen=false;
            if(lines.Count==0){preview.Text="Add an item to calculate the total.";return;}
            if(lines.Any(l=>string.IsNullOrWhiteSpace(l.Description.Text)||string.IsNullOrWhiteSpace(l.Rate.Text))){preview.Text="Enter an item description and rate to calculate the total.";foreach(var line in lines)line.Amount.Text="—";return;}
            preview.Text = "Calculating…";
            foreach(var line in lines)line.Amount.Text="—";
            try
            {
                await Task.Delay(350, request.Token);
                var body = WorkflowMasterValues.DocumentPreview(BodyValue(),previous?.Text("id")); var result = await Api.Send(Api.CompanyPath(cid, "/documents/preview"), HttpMethod.Post, body, cancellation: request.Token);
                if (!request.IsCancellationRequested) {
                    var calculated=result["data"];preview.Text = "Subtotal " + J.Money(calculated.Number("taxable")) + "   ·   GST " + J.Money(calculated.Number("cgst") + calculated.Number("sgst") + calculated.Number("igst") + calculated.Number("supplier_tax")) + "   ·   Total " + J.Money(result.Number("amount"));
                    var values=calculated?["lines"].Array()??new();for(var i=0;i<Math.Min(lines.Count,values.Count);i++)lines[i].Amount.Text=J.Money(values[i].Number("taxable")+values[i].Number("tax"));
                    if(checkCredit&&partyId.Length>0){
                        var creditParty=partyId;var asOf=date.Value;var proposed=result.Number("amount").ToString(System.Globalization.CultureInfo.InvariantCulture);
                        try{
                            var status=await Api.Send(Api.CompanyPath(cid,$"/parties/{Uri.EscapeDataString(creditParty)}/credit-status?as_of={asOf}&proposed_amount={Uri.EscapeDataString(proposed)}"),cancellation:request.Token);
                            if(!request.IsCancellationRequested&&stamp==generation&&cid==CompanyId&&partyId==creditParty&&date.Value==asOf){creditInfo.Severity=status.Flag("exceeded")?InfoBarSeverity.Warning:InfoBarSeverity.Informational;creditInfo.Message=WorkflowMasterValues.CreditStatusText(status,true);creditInfo.IsOpen=true;}
                        }catch(OperationCanceledException){}catch(Exception){if(!request.IsCancellationRequested&&stamp==generation&&partyId==creditParty){creditInfo.Severity=InfoBarSeverity.Informational;creditInfo.Message="Credit status could not be checked. Saving is still available; review the customer's balances before offering credit.";creditInfo.IsOpen=true;}}
                    }
                }
            }
            catch (OperationCanceledException) { }
            catch (Exception e) { if (!request.IsCancellationRequested) preview.Text = e.Message; }
        }
        void AddLine(JsonObject? initial = null, bool preserveImportedValues = false)
        {
            if(inlineAllowed&&lines.Count>=100){LocalError(new InvalidOperationException("An invoice supports at most100 lines."));return;}
            var line = new DocumentLine(Records.OfType<JsonObject>().Where(r => r.Text("kind") == "item" && (WorkflowMasterValues.IsActive(r)||previous is not null&&r.Text("id")==initial.Text("item_id"))), purchase, regular, initial, preserveImportedValues); var holder = Stack(6); holder.Children.Add(line.View);
            var history=Stack(8);
            if(Supports("party_price_history")&&kind is "sales_invoice" or "purchase_bill" or "estimate" or "proforma" or "sales_order" or "purchase_order"){
                holder.Children.Add(AsyncButton("Party price history / suggestion",async()=>{
                    var selectedParty=partyId;var item=line.Data().Text("item_id");
                    if(selectedParty.Length==0||item.Length==0)throw new Exception("Choose a saved party and a linked item to review price history.");
                    var result=await Api.Send(Api.CompanyPath(cid,$"/parties/{Uri.EscapeDataString(selectedParty)}/item-prices?item_id={Uri.EscapeDataString(item)}&side={(purchase?"purchase":"sales")}"));
                    if(stamp!=generation||cid!=CompanyId||partyId!=selectedParty||line.Data().Text("item_id")!=item||!lines.Contains(line))return;
                    history.Children.Clear();var rate=result.Text("suggested_rate");var includes=result.Flag("suggested_price_includes_tax");
                    history.Children.Add(Text($"Suggested {J.Money(result.Number("suggested_rate"))} · {(includes?"includes GST":"excludes GST")} · {(result.Text("source")=="last_posted"?"last posted price":"item default")}",13,true));
                    foreach(var row in result["history"].Array())history.Children.Add(Text($"{row.Text("date")} · {row.Text("number")} · qty {row.Text("quantity")} · {J.Money(row.Number("rate"))} · {(row.Flag("price_includes_tax")?"GST included":"GST extra")} · GST {row.Text("gst_rate")}% · discount {row.Text("discount_percent")}% / {row.Text("discount_amount")}",12));
                    history.Children.Add(Text("Applying changes only this line's rate and tax-inclusive basis. Current quantity, GST rate and discount remain for your review.",12));
                    history.Children.Add(Button("Apply suggested rate and tax basis",()=>{if(stamp!=generation||partyId!=selectedParty||line.Data().Text("item_id")!=item||submission.Unresolved)return;line.ApplySuggestedPrice(rate,includes);history.Children.Clear();}));
                },LocalError));holder.Children.Add(history);
            }
            holder.Children.Add(Button("Remove this item", () => { lines.Remove(line); linesPanel.Children.Remove(holder); _ = Calculate(); }));
            lines.Add(line); linesPanel.Children.Add(holder); line.Changed += () => _ = Calculate();_ = Calculate();
        }
        DocumentLine? pristineLine=null;string pristineLineData="";
        bool PristinePlaceholder()=>InlineMasterSubmission.CanReusePlaceholder(lines.Count,lines.Count==1&&ReferenceEquals(lines[0],pristineLine),lines.Count==1?lines[0].Data().ToJsonString():"",pristineLineData);
        void BeginInline(string masterKind,Control returnFocus)
        {
            if(!inlineAllowed||inlineOpen||submission.Unresolved||cid!=CompanyId||stamp!=generation||editorSession!=Api.SessionGeneration||!CanWrite)return;
            if(masterKind=="item"&&!InlineMasterSubmission.CanAppend(lines.Count))throw new InvalidOperationException("An invoice supports at most100 lines. Remove a line before creating another item.");
            var original=panel.Children.Select(child=>(Child:child,Visibility:child.Visibility)).ToArray();StackPanel? childPanel=null;inlineOpen=true;
            bool Current()=>cid==CompanyId&&stamp==generation&&editorSession==Api.SessionGeneration&&CanWrite;
            void Close(){if(childPanel is not null)panel.Children.Remove(childPanel);foreach(var entry in original)entry.Child.Visibility=entry.Visibility;inlineOpen=false;inlineCommand=null;returnFocus.Focus(FocusState.Programmatic);returnFocus.StartBringIntoView();}
            var editor=InlineMasterEditor(masterKind,cid,Current,created=>{
                if(!Current())return;
                if(!Records.Any(r=>r.Text("id")==created.Text("id")))Records.Add(created.Copy());
                created=InlineMasterSubmission.CurrentRow(Records,created);
                if(!WorkflowMasterValues.IsActive(created)){Close();LocalError(new InvalidOperationException("The master was created but is now archived. It was not selected. Refresh and review/reactivate it in Parties or Items after leaving this invoice; do not create a duplicate."));return;}
                if(masterKind=="party"){
                    var values=created["data"];partyId=created.Text("id");party.Text=created.Text("name");address.Text=values.Text("address");phone.Text=values.Text("phone");gstin.Text=values.Text("gstin");
                    var delivery=WorkflowMasterValues.ShippingAddress(values);if(shipping.Text.Length==0||shipping.Text==lastShippingDefault)shipping.Text=delivery;lastShippingDefault=delivery;
                    supply.Text=InlineMasterSubmission.PartySupplyState(created,Company.Text("state_code"));
                }else{
                    if(!InlineMasterSubmission.CanAppend(lines.Count))throw new InvalidOperationException("Item created, but invoice is full. Cancel and select it in a later invoice.");
                    if(PristinePlaceholder()){lines.Clear();linesPanel.Children.Clear();}
                    AddLine(InlineMasterSubmission.ItemLine(created,regular));
                }
                Close();_=Calculate();
            },Close);childPanel=editor.Panel;inlineCommand=editor.Submission;
            foreach(var entry in original)entry.Child.Visibility=Visibility.Collapsed;panel.Children.Insert(0,childPanel);childPanel.StartBringIntoView();
        }
        void ReplaceLines(JsonArray values, bool preserveImportedValues = false) { lines.Clear(); linesPanel.Children.Clear(); foreach (var value in values.OfType<JsonObject>()) AddLine(value,preserveImportedValues); if (lines.Count == 0) AddLine(); _ = Calculate(); }

        panel.Children.Add(SectionHeading("01",purchase?"Supplier & bill details":"Customer & document details","Choose an existing party to fill its saved details."));
        var identity=Stack(10);identity.Children.Add(party);if(inlineAllowed)identity.Children.Add(AsyncButton("+ Create customer here",()=>{BeginInline("party",party);return Task.CompletedTask;},LocalError));identity.Children.Add(regular||purchase?Columns(phone,gstin):phone);
        var metadata=Stack(10);metadata.Children.Add(Columns(number,date.View));
        if(kind is "sales_invoice" or "purchase_bill")metadata.Children.Add(regular||purchase?Columns(due.View,supply):due.View);else if(regular||purchase)metadata.Children.Add(supply);
        if(purchase)metadata.Children.Add(supplierState);
        if(Supports("party_payment_terms")&&kind is "sales_invoice" or "purchase_bill"){
            var suggestion=Stack(6);termsHint=Text(partyId.Length>0?"Suggestions use the selected saved party’s terms; applying is always explicit.":"Choose a saved party to use payment terms, or set the due date manually for a freeform name.",12);metadata.Children.Add(termsHint);termsSuggestion=AsyncButton("Suggest due date from party terms",async()=>{
                var selectedParty=partyId;var selectedDate=date.Value;
                if(selectedParty.Length==0)throw new Exception("Choose a saved party to use its payment terms.");
                var result=await Api.Send(Api.CompanyPath(cid,$"/parties/{Uri.EscapeDataString(selectedParty)}/due-date?document_date={selectedDate}"));
                if(stamp!=generation||cid!=CompanyId||partyId!=selectedParty||date.Value!=selectedDate)return;
                suggestion.Children.Clear();var proposed=result.Text("suggested_due_date");
                if(proposed.Length==0){suggestion.Children.Add(Text("This party has no saved payment terms. Edit its master or enter a due date manually.",12));return;}
                suggestion.Children.Add(Text($"{result.Text("payment_terms_days")} days · suggested due {proposed}. Your existing date is unchanged until you apply.",12));
                suggestion.Children.Add(Button("Apply suggested due date",()=>{if(stamp!=generation||partyId!=selectedParty||date.Value!=selectedDate||submission.Unresolved)return;due.Picker.Date=new DateTimeOffset(DateTime.Parse(proposed,System.Globalization.CultureInfo.InvariantCulture));suggestion.Children.Clear();}));
            },LocalError);termsSuggestion.IsEnabled=partyId.Length>0;ToolTipService.SetToolTip(termsSuggestion,"Requires a selected saved party. Freeform names do not have saved payment terms.");metadata.Children.Add(termsSuggestion);metadata.Children.Add(suggestion);
        }
        panel.Children.Add(Card(Columns(identity,metadata)));
        if (kind is "credit_note" or "debit_note")
        {
            var targetKind = kind == "credit_note" ? "sales_invoice" : "purchase_bill";
            var target = Select("Original invoice / bill", new[] { ("", "Choose a posted document") }.Concat(Records.OfType<JsonObject>().Where(r => r.Flag("posted") && (r.Text("kind") == targetKind || kind == "credit_note" && r.Text("kind") == "pos")).Select(r => (r.Text("id"), r.Text("number") + " · " + r.Text("name")))), appliedTo);
            target.SelectionChanged += async (_, _) =>
            {
                var id = Value(target); appliedTo = id; if (id.Length == 0) return; target.IsEnabled = false;sourceLoading=true;
                try { var original = await Api.Record(cid, id); if (appliedTo != id) return; party.Text = original.Text("name"); var values = original["data"]; partyId = values.Text("party_id"); address.Text = values.Text("party_address"); gstin.Text = values.Text("party_gstin"); phone.Text = values.Text("party_phone"); supply.Text = values.Text("place_of_supply"); supplierState.Text = values.Text("supplier_state") is { Length: > 0 } state ? state : values.Text("party_gstin").Length >= 2 ? values.Text("party_gstin")[..2] : Company.Text("state_code"); ReplaceLines(values?["lines"].Array() ?? new()); }
                catch (Exception e) { LocalError(e); } finally { target.IsEnabled = true;sourceLoading=false; }
            };
            panel.Children.Add(target);
        }
        var contacts = Stack(); contacts.Children.Add(Columns(address, shipping));
        panel.Children.Add(new Expander { Header = "Party, billing and delivery details", Content = contacts, HorizontalContentAlignment = HorizontalAlignment.Stretch, HorizontalAlignment = HorizontalAlignment.Stretch });
        party.TextChanged += (sender, args) => { if (args.Reason == AutoSuggestionBoxTextChangeReason.UserInput) { partyId = "";address.Text="";if(shipping.Text==lastShippingDefault)shipping.Text="";lastShippingDefault="";gstin.Text="";phone.Text="";supply.Text=Company.Text("state_code");supplierState.Text=Company.Text("state_code");party.ItemsSource = Records.OfType<JsonObject>().Where(r => r.Text("kind") == "party" && WorkflowMasterValues.IsActive(r) && r.Text("name").Contains(party.Text, StringComparison.OrdinalIgnoreCase)).Take(20).Select(r => r.Text("name")).ToArray(); _=Calculate(); } };
        party.SuggestionChosen += (sender, args) => { var selected = Records.OfType<JsonObject>().FirstOrDefault(r => r.Text("kind") == "party" && WorkflowMasterValues.IsActive(r) && r.Text("name") == args.SelectedItem?.ToString()); if (selected is null) return; partyId = selected.Text("id"); var values = selected["data"]; address.Text = values.Text("address"); var delivery=Supports("party_shipping_address")?WorkflowMasterValues.ShippingAddress(values):values.Text("address");if(shipping.Text.Length==0||shipping.Text==lastShippingDefault)shipping.Text=delivery;lastShippingDefault=delivery; gstin.Text = values.Text("gstin"); phone.Text = values.Text("phone"); if (gstin.Text.Length >= 2) { if (purchase) supplierState.Text = gstin.Text[..2]; else supply.Text = gstin.Text[..2]; } _=Calculate(); };
        if (kind == "purchase_bill")
        {
            var ocr = AsyncButton("Scan purchase bill", async () =>
            {
                var file = await ApexFiles.Pick(".png", ".jpg", ".jpeg", ".webp"); if (file is null) return;
                var image = await ApexFiles.Image(file, 3000, 2_700_000); var result = await Api.Send(Api.CompanyPath(cid, "/ocr/purchase-draft"), HttpMethod.Post, new JsonObject { ["image_data_url"] = image }); var draft = result["draft"];
                partyId = ""; phone.Text = ""; shipping.Text = ""; due.Picker.Date = null; discount.Text = "0"; round.IsChecked = false;
                party.Text = draft.Text("supplier_name"); number.Text = draft.Text("invoice_number"); address.Text = draft.Text("supplier_address"); gstin.Text = draft.Text("supplier_gstin"); supplierState.Text = gstin.Text.Length >= 2 ? gstin.Text[..2] : Company.Text("state_code"); supply.Text = draft.Text("place_of_supply").Length == 2 ? draft.Text("place_of_supply") : Company.Text("state_code");
                if (DateTime.TryParse(draft.Text("invoice_date"), out var extractedDate)) date.Picker.Date = new DateTimeOffset(extractedDate);
                ReplaceLines(draft?["items"].Array() ?? new(),true); info.Severity = InfoBarSeverity.Warning; info.Message = "Draft extracted. Bill total: " + draft.Text("total") + ". Linking stock keeps the scanned rate and GST. Review every field before posting."; info.IsOpen = true;
            }, LocalError); panel.Children.Add(ocr);
        }
        panel.Children.Add(SectionHeading("02","Items & services","Select an item or enter a description. Tax and totals are calculated automatically."));
        panel.Children.Add(linesPanel); ReplaceLines(data["lines"].Array()); panel.Children.Add(Button("+ Add item", () => AddLine()));
        if(inlineAllowed){pristineLine=lines.Count==1?lines[0]:null;pristineLineData=pristineLine?.Data().ToJsonString()??"";Button? createItem=null;createItem=AsyncButton("+ Create item here",()=>{BeginInline("item",createItem!);return Task.CompletedTask;},LocalError);panel.Children.Add(createItem);}
        panel.Children.Add(SectionHeading("03","Adjustments & notes","Review the final amounts before saving."));
        if(kind is "credit_note" or "debit_note"){
            fixedReviewBox=new CheckBox{Content="I reviewed the fixed ₹ line discounts against the quantities being returned"};panel.Children.Add(Text("Fixed ₹ discounts are copied unchanged from the source. They are not automatically prorated when return quantities change; review each affected line.",12));panel.Children.Add(fixedReviewBox);
            if(previous is not null){fixedReview.Acknowledge(FixedSignature());fixedReviewBox.IsChecked=true;}
            fixedReviewBox.Checked+=(_,_)=>fixedReview.Acknowledge(FixedSignature());fixedReviewBox.Unchecked+=(_,_)=>fixedReview.Clear();UpdateFixedReview();
        }else if(conversion is not null&&lines.Any(line=>line.Data().Number("discount_amount")>0))panel.Children.Add(Text("Fixed ₹ line discounts were preserved from the source draft. Review them if changing quantities; no automatic prorating is applied.",12));

        panel.Children.Add(Columns(discount, round)); if (kind is "credit_note" or "debit_note") panel.Children.Add(returnStock);
        if (kind is "expense" or "pos")
        {
            void ShowPayment(){bank.Visibility=Value(method)=="bank"?Visibility.Visible:Visibility.Collapsed;tender.Visibility=kind=="pos"&&Value(method)=="cash"?Visibility.Visible:Visibility.Collapsed;}
            method.SelectionChanged+=(_,_)=>ShowPayment();ShowPayment();
            panel.Children.Add(Columns(method,bank));if(kind=="expense")panel.Children.Add(category);else panel.Children.Add(tender);
        }
        panel.Children.Add(new Expander{Header="Notes & terms",Content=Columns(notes,terms),HorizontalContentAlignment=HorizontalAlignment.Stretch,HorizontalAlignment=HorizontalAlignment.Stretch});
        date.Picker.DateChanged+=(_,_)=>_=Calculate();
        var totals=Stack(6);totals.Children.Add(preview);if(checkCredit)totals.Children.Add(creditInfo);var shortcut=Text("Ctrl + Enter to save · totals calculated by Apex Books",12);shortcut.Foreground=Muted;totals.Children.Add(shortcut);
        discount.TextChanged += (_, _) => _ = Calculate(); supply.TextChanged += (_, _) => _ = Calculate(); supplierState.TextChanged += (_, _) => _ = Calculate(); gstin.TextChanged += (_, _) => {if(purchase&&gstin.Text.Length>=2&&gstin.Text.Take(2).All(char.IsDigit))supplierState.Text=gstin.Text[..2];_=Calculate();}; round.Checked += (_, _) => _ = Calculate(); round.Unchecked += (_, _) => _ = Calculate();
        var baseline=BodyValue().ToJsonString();var keepNew=false;
        async Task Save()
        {
            if(inlineOpen)throw new Exception("Finish or cancel the inline master creation before saving this invoice.");
            if(sourceLoading)throw new Exception("Wait for the source document to finish loading.");
            if(!submission.Unresolved&&NeedsFixedReview()&&!fixedReview.IsAcknowledged(FixedSignature()))throw new Exception("Review each fixed ₹ discount against the quantities being returned, then acknowledge the review before saving.");
            if (party.Text.Trim().Length == 0) throw new Exception("Enter the customer, supplier or description.");
            if (lines.Count == 0) throw new Exception("Add at least one item.");
            if(!submission.Unresolved&&previous is null&&kind is not ("credit_note" or "debit_note")){
                if(partyId.Length>0&&Records.FirstOrDefault(r=>r.Text("id")==partyId) is { } selectedParty&&!WorkflowMasterValues.IsActive(selectedParty))throw new Exception("This party is archived. Choose an active party or reactivate it before creating a new document.");
                if(lines.Any(line=>Records.FirstOrDefault(r=>r.Text("id")==line.Data().Text("item_id")) is { } item&&!WorkflowMasterValues.IsActive(item)))throw new Exception("A linked item is archived. Choose active items or reactivate them before creating a new document.");
            }
            if (kind is "credit_note" or "debit_note" && appliedTo.Length == 0) throw new Exception("Choose the original posted document.");
            try{await Api.SaveRecord(cid, submission.Body(BodyValue()), retryKey, previous);submission.Succeeded();}
            catch(Exception e){submission.Failed(e);NativeUi.SetFormEnabled(panel,!submission.Unresolved);if(submission.Unresolved)throw new Exception("The save outcome is unknown. The original values are locked; press Save again to safely recover the same document.",e);throw;}
        }
        var saved = await Dialog((previous is not null ? "Edit " : "New ") + FeatureCatalog.Singular(kind), panel, Save,
            previous is null ? "Save " + (kind=="purchase_bill"?"bill":kind=="sales_invoice"?"invoice":"document") : "Save changes",
            canSave:()=>!sourceLoading&&!inlineOpen,unresolved:()=>submission.Unresolved||inlineCommand?.Unresolved==true,hasChanges:()=>inlineOpen||BodyValue().ToJsonString()!=baseline,
            saveAndNew:previous is null&&conversion is null?async()=>{await Save();keepNew=true;}:null,stickyFooter:Card(totals));
        previewRequest?.Cancel(); if (saved && cid == CompanyId) await Refresh();
        if(saved&&keepNew&&cid==CompanyId)await EditDocument(kind);
    }
}
