import { lazy, Suspense } from "react";
import type { MonacoProps } from "./MonacoEditor";
import { Skeleton } from "./ui/skeleton";

const Monaco = lazy(() => import("./MonacoEditor"));

export function CodeEditor(props: MonacoProps) {
  return (
    <Suspense fallback={<Skeleton className="w-full" />}>
      <Monaco {...props} />
    </Suspense>
  );
}
