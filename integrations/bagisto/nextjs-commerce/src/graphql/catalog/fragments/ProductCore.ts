import { gql } from "@apollo/client";

export const PRODUCT_CORE_FRAGMENT = gql`
  fragment ProductCore on Product {
    id
    sku
    type
    name
    price
    urlKey
    baseImageUrl
    minimumPrice
    specialPrice
    isSaleable
  }
`;
