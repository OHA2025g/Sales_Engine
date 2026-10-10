export function PublishedPostLink({
  href,
  status,
  className = "btn",
}: {
  href?: string;
  status: string;
  className?: string;
}) {
  if (status !== "published" || !href?.startsWith("https://")) return null;
  return (
    <a className={className} href={href} target="_blank" rel="noreferrer">
      View post
    </a>
  );
}
