import AccountPagination from "../AccountPagination";

export default function DownloadableProductPagination(props: {
  totalPages: number;
  currentPage: number;
  nextCursor?: string;
  prevCursor?: string;
}) {
  return <AccountPagination {...props} />;
}

