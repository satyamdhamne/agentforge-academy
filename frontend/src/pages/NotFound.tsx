import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="py-20 text-center">
      <p className="font-mono text-sm text-faint">404</p>
      <h1 className="mt-2 text-3xl font-semibold">This page doesn’t exist</h1>
      <p className="mt-2 text-muted">The link may be old, or the content may have moved.</p>
      <Button asChild className="mt-6"><Link to="/paths">Browse learning paths</Link></Button>
    </div>
  );
}
