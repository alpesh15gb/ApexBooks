import { gql } from "@apollo/client";


export const GET_FILTER_ATTRIBUTES = gql`
  query GetFilterAttributesBatch {
    color: attribute(id: "/api/admin/attributes/23") {
      id
      code
      options {
        edges {
          node {
            id
            adminName
            translations {
              edges {
                node {
                  id
                  label
                  locale
                }
              }
            }
          }
        }
      }
    }
    size: attribute(id: "/api/admin/attributes/24") {
      id
      code
      options {
        edges {
          node {
            id
            adminName
            translations {
              edges {
                node {
                  id
                  label
                  locale
                }
              }
            }
          }
        }
      }
    }
    brand: attribute(id: "/api/admin/attributes/25") {
      id
      code
      options {
        edges {
          node {
            id
            adminName
            translations {
              edges {
                node {
                  id
                  label
                  locale
                }
              }
            }
          }
        }
      }
    }
  }
`;