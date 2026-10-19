import { cloneElement, forwardRef, isValidElement, type HTMLAttributes, type ReactElement } from "react";
import { cn } from "@/lib/utils";

/** Minimal Radix-style Slot: merges props/className onto the single child element. */
export const Slot = forwardRef<HTMLElement, HTMLAttributes<HTMLElement>>(({ children, className, ...props }, ref) => {
  if (!isValidElement(children)) return null;
  const child = children as ReactElement<Record<string, unknown>>;
  return cloneElement(child, { ...props, ...child.props, ref, className: cn(className, child.props.className as string) });
});
Slot.displayName = "Slot";
