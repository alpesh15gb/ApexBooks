import { gql } from "@apollo/client";

export const GET_CHECKOUT_ADDRESSES = gql`
 query collectionGetCheckoutAddresses {
collectionGetCheckoutAddresses {
      edges {
        node {
          id
          addressType
          firstName
          lastName
          companyName
          vatId
          address
          city
          state
          country
          postcode
          email
          phone
          defaultAddress
          useForShipping
        }
      }
    }
  }
`;
