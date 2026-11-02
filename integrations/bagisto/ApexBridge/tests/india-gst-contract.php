<?php
require __DIR__.'/../src/IndiaGstState.php';
require __DIR__.'/../src/IndiaGstin.php';
require __DIR__.'/../src/Bridge.php';
use ApexBooks\Bridge\IndiaGstState;
use ApexBooks\Bridge\IndiaGstin;
$checks=0;
$check=function($ok,$label)use(&$checks){if(!$ok)throw new RuntimeException($label);$checks++;};
$states=json_decode(file_get_contents(__DIR__.'/../resources/india-gst-states.json'),true,512,JSON_THROW_ON_ERROR)['states'];
foreach($states as $code=>$name){$code=str_pad((string)$code,2,'0',STR_PAD_LEFT);$check(IndiaGstState::resolve($name,[],$code==='25'?'2019-01-01':'2026-11-02')===$code,'GSTN state '.$code);}
foreach(['TN'=>'33','TG'=>'36','TS'=>'36','UK'=>'05','OR'=>'21','PY'=>'34','DD'=>'26','Dadra & Nagar Haveli'=>'26','Lakshadweep'=>'31']as$state=>$code)$check(IndiaGstState::resolve($state)===$code,'Regional alias '.$state);
$check(IndiaGstState::resolve('unknown')===null,'Unknown state must not default');
$check(IndiaGstState::resolve('TN',['TN'=>'99'])===null,'Invalid override must not post');
$check(IndiaGstin::valid('27ABCDE1234F1Z0'),'Valid GSTIN checksum');
$check(!IndiaGstin::valid('27ABCDE1234F1Z1'),'Invalid GSTIN checksum');
$check(!IndiaGstin::valid('99ABCDE1234F1Z0'),'Unknown GSTIN state');
$bridge=new \ApexBooks\Bridge\Bridge;
$order=(object)['id'=>100,'customer_id'=>12,'billing_address'=>(object)['vat_id'=>'27BBBBB0000B1ZT']];
$check($bridge->customerId($order)==='customer:12:gst:27BBBBB0000B1ZT','Registered business identity is scoped by GSTIN');
$order->billing_address->vat_id='';$check($bridge->customerId($order)==='customer:12','Personal checkout keeps the account identity');
$order->customer_id=null;$check($bridge->customerId($order)==='guest:100','Guest identity stays tied to its accepted order');
echo json_encode(['passed'=>$checks]).PHP_EOL;
