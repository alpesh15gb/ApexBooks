
import { ProductData } from "../type";
import { ProductDescription } from "./ProductDescription";
import { ProductSwatchReview } from "@/types/category/type";
import { getProductReviews } from "@utils/hooks/getProductReviews";

export default async function ProductInfo({
  product,
  slug,
}: {
  product: ProductData;
  slug: string;
}) {
  const reviews = await getProductReviews(product?.id?.split("/").pop() || "");

  return (
    <ProductDescription
      product={product}
      productSwatchReview={product as unknown as ProductSwatchReview}
      slug={slug}
      reviews={reviews}
      totalReview={reviews.length}
      avgRating={reviews.reduce((sum, r) => sum + (r.node.rating ?? 0), 0) / (reviews.length || 1)}
    />
  );
}
