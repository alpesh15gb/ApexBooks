import OpenGraphImage from "@components/common/OpenGraphImage";
import { getPage } from "@utils/bagisto";

export default async function Image({ params }: { params: { page: string } }) {
  const page = await getPage({ urlKey: params.page }) as { translation?: { metaTitle?: string; pageTitle?: string } }[];
  const pageData = page && page.length > 0 ? page[0].translation : undefined;
  const title = pageData?.metaTitle || pageData?.pageTitle;

  return await OpenGraphImage({ title });
}
