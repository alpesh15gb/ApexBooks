import AccountPagination from "../AccountPagination";

export default function ReviewPagination(props: {
  totalPages: number;
  currentPage: number;
  nextCursor?: string;
  prevCursor?: string;
}) {
  return <AccountPagination {...props} />;
}

