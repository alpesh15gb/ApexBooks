<?php
namespace ApexBooks\Bridge\Compatibility;
use ApiPlatform\Metadata\Operations;
use ApiPlatform\Metadata\Resource\Factory\ResourceMetadataCollectionFactoryInterface;
use ApiPlatform\Metadata\Resource\ResourceMetadataCollection;

final class GstCheckoutMetadata implements ResourceMetadataCollectionFactoryInterface
{
    public function __construct(private readonly ResourceMetadataCollectionFactoryInterface $inner){}
    public function create(string $resourceClass): ResourceMetadataCollection
    {
        $result=clone $this->inner->create($resourceClass);
        foreach($result as $position=>$resource){
            if(($operations=$resource->getOperations())!==null){$updated=[];foreach($operations as $name=>$operation)$updated[$name]=$this->adapt($operation);$resource=$resource->withOperations(new Operations($updated));}
            if(($operations=$resource->getGraphQlOperations())!==null){$updated=[];foreach($operations as $name=>$operation)$updated[$name]=$this->adapt($operation);$resource=$resource->withGraphQlOperations($updated);}
            $result[$position]=$resource;
        }
        return $result;
    }
    private function adapt($operation)
    {
        $input=$operation->getInput();
        if($input===\Webkul\BagistoApi\Dto\CheckoutAddressInput::class || is_array($input)&&($input['class']??null)===\Webkul\BagistoApi\Dto\CheckoutAddressInput::class) $operation=$operation->withInput(array_replace(is_array($input)?$input:[],['class'=>GstCheckoutInput::class]));
        if($operation->getProcessor()===\Webkul\BagistoApi\State\CheckoutProcessor::class)$operation=$operation->withProcessor(GstCheckoutProcessor::class);
        return $operation;
    }
}
