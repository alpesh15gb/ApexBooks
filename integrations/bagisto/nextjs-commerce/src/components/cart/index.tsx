import CartModal from "./CartModal";

export default function Cart({
  children,
  className,
  onOpen,
  onClose,
  isOpen,
}: {
  children?: React.ReactNode;
  className?: string;
  onOpen?: () => void;
  onClose?: () => void;
  isOpen?: boolean;
}) {
  return (
    <CartModal className={className} onOpen={onOpen} onClose={onClose} isOpen={isOpen}>
      {children}
    </CartModal>
  );
}
