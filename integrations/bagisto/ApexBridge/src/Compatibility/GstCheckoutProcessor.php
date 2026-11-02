<?php
namespace ApexBooks\Bridge\Compatibility;
use ApiPlatform\Metadata\Operation;
use ApexBooks\Bridge\IndiaGstState;
use ApexBooks\Bridge\IndiaGstin;
use Webkul\Checkout\Facades\Cart;
use Illuminate\Support\Facades\Request;
use Webkul\BagistoApi\Facades\CartTokenFacade;
use Webkul\BagistoApi\Facades\TokenHeaderFacade;
use Webkul\BagistoApi\Exception\OperationFailedException;

final class GstCheckoutProcessor extends \Webkul\BagistoApi\State\CheckoutProcessor
{
    public static function validGstin(string $value): bool
    {
        return IndiaGstin::valid($value);
    }
    public function process(mixed $data, Operation $operation, array $uriVariables=[], array $context=[]): mixed
    {
        $address=class_basename($operation->getClass()??'')==='CheckoutAddress';
        $gstin=$address && $data instanceof GstCheckoutInput ? $data->billingGstin : null;
        if($gstin!==null){
            $gstin=strtoupper(trim($gstin));
            if($gstin!=='' && (strtoupper((string)$data->billingCountry)!=='IN' || !self::validGstin($gstin))) throw new OperationFailedException('Enter a valid Indian GSTIN, or leave it blank for a personal purchase.');
            if($gstin!=='' && IndiaGstState::resolve((string)$data->billingState)!==substr($gstin,0,2)) throw new OperationFailedException('The billing state must match the business GSTIN state.');
        }
        $result=parent::process($data,$operation,$uriVariables,$context);
        if($address && $gstin!==null){
            $request=Request::instance()??($context['request']??null);
            $token=$request?TokenHeaderFacade::getAuthorizationBearerToken($request):null;
            $cart=$token?CartTokenFacade::getCartByToken($token):null;
            if($cart) $cart->billing_address()->update(['vat_id'=>$gstin?:null]);
        }
        return $result;
    }
}
