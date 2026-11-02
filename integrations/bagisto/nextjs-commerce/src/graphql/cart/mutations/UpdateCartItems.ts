import { gql } from "@apollo/client";

export const UPDATE_CART_ITEM = gql
  `
  mutation UpdateCartItem(
    $cartItemId: Int!
    $quantity: Int!
  ) {
    createUpdateCartItem(
      input: {
        cartItemId: $cartItemId
        quantity: $quantity
      }
    ) {
      updateCartItem {
        id
         taxAmount: taxTotal
         discountAmount
        shippingAmount
        subtotal
        grandTotal
        items {
          edges {
            node {
              id
              cartId
              productId
              name
               price
               baseImage
              sku
              quantity
              type
              productUrlKey
              canChangeQty
            }
          }
        }
          itemsQty
        grandTotal
      }
    }
  }
`;
