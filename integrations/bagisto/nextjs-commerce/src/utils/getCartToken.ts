import { GUEST_CART_TOKEN, GUEST_CART_ID, IS_GUEST } from "@/utils/constants";
import { decodeJWT, encodeJWT } from "@/utils/jwt-cookie";

export const getNativeCookie = (name: string): string | null => {
  if (typeof document === "undefined") return null;

  const cookies = document.cookie.split("; ").map((c) => c.trim());
  const found = cookies.find((c) => c.startsWith(name + "="));
  return found ? decodeURIComponent(found.split("=")[1]) : null;
};

export const getCartToken = (): string | null => {
  const raw = getNativeCookie(GUEST_CART_TOKEN);
  if (!raw) return null;

  const isGuest = getNativeCookie(IS_GUEST) !== "false";

  const decoded = decodeJWT<{ sessionToken: string }>(raw, isGuest);
  return decoded?.sessionToken ?? null;
};


export const getGuestCartId = (): number | null => {
  const raw = getNativeCookie(GUEST_CART_ID);
  if (!raw) return null;
  const id = parseInt(raw, 10);
  return isNaN(id) ? null : id;
};

export const getCookie = (name: string): string | null => {
  if (typeof document === "undefined") return null;

  const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
  return match ? decodeURIComponent(match[2]) : null;
};

export const setCookie = (name: string, value: string, days = 7) => {
  if (typeof document === "undefined") return;
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${name}=${value}; expires=${expires}; path=/; SameSite=Lax${secure}`;
};

export const deleteCookie = (name: string) => {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; Max-Age=0; path=/`;
};

// Add-to-cart may replace an inactive guest cart and return a new capability.
// Persist that authoritative identity before any subsequent address/cart request.
export const rememberGuestCart = (token: string, cartId?: string | number | null) => {
  if (!token || getCookie(IS_GUEST) === "false") return;
  setCookie(GUEST_CART_TOKEN, encodeJWT({ sessionToken: token, cartId, isGuest: true }));
  if (cartId != null && Number.isFinite(Number(cartId))) setCookie(GUEST_CART_ID, String(cartId));
  setCookie(IS_GUEST, "true");
};

export const clearCompletedGuestCart = () => {
  if (getCookie(IS_GUEST) === "false") return;
  deleteCookie(GUEST_CART_TOKEN);
  deleteCookie(GUEST_CART_ID);
};
