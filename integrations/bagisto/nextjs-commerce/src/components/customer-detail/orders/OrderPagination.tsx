import AccountPagination from "../AccountPagination";

export default function OrderPagination(props: {
  totalPages: number;
  currentPage: number;
  nextCursor?: string;
  prevCursor?: string;
}) {
  return <AccountPagination {...props} />;
}

