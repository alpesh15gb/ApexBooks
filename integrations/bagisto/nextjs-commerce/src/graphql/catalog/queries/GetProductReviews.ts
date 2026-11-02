import { gql } from "@apollo/client";

export const GET_PRODUCT_REVIEWS = gql`
  query ProductReview($first: Int, $product_id: Int!) {
    productReviews(first: $first, product_id: $product_id) {
      edges {
        node {
          name
          title
          rating
          comment
          createdAt
        }
      }
    }
  }
`;
