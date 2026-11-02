import { safeParse } from "../helper";

interface VariantOption {
  id?: string | number;
  [key: string]: unknown;
}

export interface VariantSuperAttribute {
  id?: string;
  code: string;
  label?: string;
  adminName?: string;
  type?: string;
  swatchType?: string;
  swatchValue?: string;
  options?: VariantOption[] | { edges?: Array<{ node: VariantOption }> };
  [key: string]: unknown;
}

export const getVariantInfo = (
  isConfigurable: boolean,
  params: string,
  superAttributes: VariantSuperAttribute[],
  index: string
) => {
  if (!isConfigurable) {
    return {
      Instock: false,
      productid: "",
      possibleOptions: {},
      variantAttributes: superAttributes,
    };
  }
  const searchParams = new URLSearchParams(params);
  const indexData: Record<string, Record<string, number>> =
    safeParse(index) || {};

  const selectedAttributes: Record<string, number> = {};

  for (const attr of superAttributes) {
    const value = searchParams.get(attr.code);
    if (value) {
      selectedAttributes[attr.code] = Number(value);
    }
  }

  const possibleOptions: Record<string, number[]> = {};

  if (Object.keys(selectedAttributes).length === 0) {
    for (const attr of superAttributes) {
      possibleOptions[attr.code] = [];
    }
  } else {
    const attrValueToVariantIds: Record<string, Record<number, Set<string>>> = {};

    for (const [variantId, attrs] of Object.entries(indexData)) {
      for (const [code, value] of Object.entries(attrs)) {
        if (!attrValueToVariantIds[code]) {
          attrValueToVariantIds[code] = {};
        }
        if (!attrValueToVariantIds[code][value]) {
          attrValueToVariantIds[code][value] = new Set();
        }
        attrValueToVariantIds[code][value].add(variantId);
      }
    }

    for (const attr of superAttributes) {
      const otherSelectedAttributes = { ...selectedAttributes };
      delete otherSelectedAttributes[attr.code];

      let compatibleVariantIds: Set<string> | null = null;

      for (const [code, value] of Object.entries(otherSelectedAttributes)) {
        const variantIds = attrValueToVariantIds[code]?.[value];
        if (!variantIds) {
          compatibleVariantIds = new Set();
          break;
        }
        if (compatibleVariantIds === null) {
          compatibleVariantIds = new Set(variantIds);
        } else {
          const currentIds = [...compatibleVariantIds] as string[];
          compatibleVariantIds = new Set(
            currentIds.filter((id) => (variantIds || new Set()).has(id)),
          );
        }
      }

      if (compatibleVariantIds === null) {
        compatibleVariantIds = new Set(Object.keys(indexData));
      }

      possibleOptions[attr.code] = [...compatibleVariantIds]
        .map((id) => indexData[id]?.[attr.code])
        .filter((val): val is number => val !== undefined);
    }
  }

  const variantAttributes = superAttributes.map((attr) => {
    const rawOptions = Array.isArray(attr.options)
      ? attr.options
      : attr.options?.edges?.map((edge) => edge.node) || [];

    return {
      ...attr,
      options: rawOptions.map((option) => ({
        ...option,
        isValid: (() => {
          const otherSelectedAttributes = { ...selectedAttributes };
          delete otherSelectedAttributes[attr.code];
          const hasOtherSelections =
            Object.keys(otherSelectedAttributes).length > 0;
          return (
            !hasOtherSelections ||
            possibleOptions[attr.code].includes(Number(option.id))
          );
        })(),
      })),
    };
  });

  const allSelected = superAttributes.every(
    (attr) => selectedAttributes[attr.code] !== undefined,
  );

  const matchingVariants = Object.entries(indexData).filter(([_, attributes]) =>
    Object.entries(selectedAttributes).every(
      ([code, value]) => attributes[code] === value,
    ),
  );

  if (allSelected && matchingVariants.length > 0) {
    return {
      productid: matchingVariants[0][0],
      Instock: true,
      possibleOptions,
      variantAttributes,
    };
  }

  return {
    productid: "",
    Instock: matchingVariants.length > 0,
    possibleOptions,
    variantAttributes,
  };
};
