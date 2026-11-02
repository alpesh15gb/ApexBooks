<?php
namespace ApexBooks\Bridge\Compatibility;
use ApiPlatform\Metadata\Operations;
use ApiPlatform\Metadata\Resource\Factory\ResourceMetadataCollectionFactoryInterface;
use ApiPlatform\Metadata\Resource\ResourceMetadataCollection;

final class PostgresProductMetadata implements ResourceMetadataCollectionFactoryInterface
{
    public function __construct(private readonly ResourceMetadataCollectionFactoryInterface $inner) {}
    public function create(string $resourceClass): ResourceMetadataCollection
    {
        $result = clone $this->inner->create($resourceClass);
        foreach ($result as $position => $resource) {
            $operations = $resource->getOperations();
            if ($operations !== null) {
                $updated = [];
                foreach ($operations as $name => $operation) $updated[$name] = $this->adapt($operation);
                $resource = $resource->withOperations(new Operations($updated));
            }
            $operations = $resource->getGraphQlOperations();
            if ($operations !== null) {
                $updated = [];
                foreach ($operations as $name => $operation) $updated[$name] = $this->adapt($operation);
                $resource = $resource->withGraphQlOperations($updated);
            }
            $result[$position] = $resource;
        }
        return $result;
    }
    private function adapt($operation)
    {
        return $operation->getProvider() === \Webkul\BagistoApi\State\ProductGraphQLProvider::class
            ? $operation->withProvider(PostgresProductProvider::class) : $operation;
    }
}
