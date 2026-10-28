import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <h1 className="font-wide text-3xl font-bold tracking-tight">Nothing here</h1>
      <p className="mt-2 text-ink-2">That page doesn&rsquo;t exist on the floor.</p>
      <Link href="/" className="mt-6 inline-block underline">
        Go to the floor
      </Link>
    </div>
  );
}
