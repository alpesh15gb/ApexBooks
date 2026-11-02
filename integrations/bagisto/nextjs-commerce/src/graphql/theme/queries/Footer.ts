import { gql } from "@apollo/client";

export const GET_FOOTER = gql`
  query footerQuery($type: String) {
    themeCustomizations: sections(type: $type) {
      edges {
        node {
          id
          type
          name
          status
          translations {
            edges {
              node {
                id
                themeCustomizationId: sectionId
                locale
                options
              }
            }
          }
        }
      }
    }
  }
`;
