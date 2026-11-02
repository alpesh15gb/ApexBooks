import { HTMLAttributes } from "react";

interface ShimmerProps extends HTMLAttributes<HTMLDivElement> {
  className?: string;
  rounded?: string;
  width?: string | number;
  height?: string | number;
}

export function Shimmer({
  className,
  rounded = "rounded-md",
  width = "100%",
  height = "100%",
  ...props
}: ShimmerProps) {
  const roundedClass = rounded.startsWith("rounded")
    ? rounded
    : `rounded-${rounded}`;

  return (
    <div
      className={`
        relative overflow-hidden
        bg-neutral-200 dark:bg-neutral-800
        ${roundedClass}
        ${className ?? ""}
      `}
      style={{ width, height }}
      {...props}
    >
      <div
        className="
          absolute inset-0 -translate-x-full
          animate-[shimmer_1.6s_ease-in-out_infinite]
          bg-gradient-to-r from-transparent via-white/50 dark:via-white/10 to-transparent
        "
      />
    </div>
  );
}