"use client";

import { useSearchParams, usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import { ChevronLeftIcon, ChevronRightIcon } from "@heroicons/react/24/outline";
import { createUrl } from "@/utils/helper";

export default function AccountPagination({
  totalPages,
  currentPage,
  nextCursor,
  prevCursor,
}: {
  totalPages: number;
  currentPage: number;
  nextCursor?: string;
  prevCursor?: string;
  activeClassName?: string;
  inactiveClassName?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const handlePageChange = (page: number) => {
    if (page < 1 || page > totalPages) return;

    const params = new URLSearchParams(searchParams.toString());
    params.set("page", String(page));

    if (page === currentPage + 1 && nextCursor) {
      params.set("cursor", nextCursor);
      params.delete("before");
    } else if (page === currentPage - 1 && prevCursor) {
      params.set("before", prevCursor);
      params.delete("cursor");
    } else {
      params.delete("cursor");
      params.delete("before");
    }

    const newUrl = createUrl(pathname, params);
    router.push(newUrl);
  };

  const renderDots = () => {
    const dots = [];
    const maxVisiblePages = 5;

    if (totalPages <= maxVisiblePages) {
      for (let i = 1; i <= totalPages; i++) {
        dots.push(renderPageButton(i));
      }
    } else {
      const halfMax = Math.floor(maxVisiblePages / 2);
      let start = Math.max(1, currentPage - halfMax);
      let end = Math.min(totalPages, start + maxVisiblePages - 1);

      if (end - start + 1 < maxVisiblePages) {
        start = Math.max(1, totalPages - maxVisiblePages + 1);
      }

      if (start > 1) {
        dots.push(renderPageButton(1));
        if (start > 2) {
          dots.push(
            <li key="dot-start" className="flex h-8 w-8 sm:h-10 sm:w-10 items-center justify-center text-xs sm:text-base text-gray-500 dark:text-gray-400">
              ...
            </li>
          );
        }
      }

      for (let i = start; i <= end; i++) {
        dots.push(renderPageButton(i));
      }

      if (end < totalPages) {
        if (end < totalPages - 1) {
          dots.push(
            <li key="dot-end" className="flex h-8 w-8 sm:h-10 sm:w-10 items-center justify-center text-xs sm:text-base text-gray-500 dark:text-gray-400">
              ...
            </li>
          );
        }
        dots.push(renderPageButton(totalPages));
      }
    }

    return dots;
  };

  const renderPageButton = (page: number) => (
    <li
      key={page}
      onClick={() => handlePageChange(page)}
      className="rounded-sm cursor-pointer"
    >
      <button
        className={clsx(
          "flex h-8 w-8 sm:h-10 sm:w-10 items-center justify-center text-sm sm:text-base rounded-sm duration-300 cursor-pointer",
          page === currentPage
            ? "border !border-gray-300 dark:border-gray-700 font-medium text-black dark:text-white"
            : "text-gray-500 dark:!text-gray-400 hover:border-gray-500 dark:hover:border-gray-700"
        )}
        aria-label={`Goto Page ${page}`}
        aria-current={page === currentPage}
      >
        {page}
      </button>
    </li>
  );

  if (totalPages <= 1) return null;

  return (
    <ul
      className="gap-x-1 sm:gap-x-2 text-sm sm:text-base flex flex-wrap justify-center items-center"
      role="navigation"
      aria-label="Pagination"
    >
      <li
        key="prev"
        onClick={() => handlePageChange(currentPage - 1)}
        className={clsx(
          "rounded-lg hover:text-gray-700",
          currentPage > 1 ? "cursor-pointer" : ""
        )}
      >
        <button
          className={clsx(
            "ml-0 flex h-8 sm:h-10 items-center justify-center px-1.5 sm:px-2 leading-tight text-black dark:text-white",
            currentPage > 1 ? "cursor-pointer" : "cursor-not-allowed opacity-40"
          )}
          aria-label="Previous page"
          disabled={currentPage <= 1}
        >
          <ChevronLeftIcon className="h-4 w-4 sm:h-5 sm:w-5" />
        </button>
      </li>

      {renderDots()}

      <li
        key="next"
        onClick={() => handlePageChange(currentPage + 1)}
        className={clsx(
          "rounded-lg hover:text-gray-700",
          currentPage < totalPages ? "cursor-pointer" : ""
        )}
      >
        <button
          className={clsx(
            "ml-0 flex h-8 sm:h-10 items-center justify-center px-1.5 sm:px-2 leading-tight text-black dark:text-white",
            currentPage < totalPages ? "cursor-pointer" : "cursor-not-allowed opacity-40"
          )}
          aria-label="Next page"
          disabled={currentPage >= totalPages}
        >
          <ChevronRightIcon className="h-4 w-4 sm:h-5 sm:w-5" />
        </button>
      </li>
    </ul>
  );
}
