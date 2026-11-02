<?php
namespace ApexBooks\Bridge\Compatibility;
use ApiPlatform\Metadata\ApiProperty;
use Symfony\Component\Serializer\Annotation\Groups;
use Symfony\Component\Serializer\Annotation\SerializedName;

final class GstCheckoutInput extends \Webkul\BagistoApi\Dto\CheckoutAddressInput
{
    #[Groups(['mutation'])]
    #[ApiProperty(description: 'Optional Indian business GSTIN')]
    #[SerializedName('billingGstin')]
    public ?string $billingGstin = null;
}
