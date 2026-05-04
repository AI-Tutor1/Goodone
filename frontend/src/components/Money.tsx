// Render a money value with currency + 2 dp. Defaults to AED.

interface Props {
  amount: string | number | null | undefined;
  currency?: "AED" | "PKR";
  className?: string;
}

export function Money({ amount, currency = "AED", className = "" }: Props) {
  if (amount === null || amount === undefined || amount === "") {
    return <span className={className}>—</span>;
  }
  const n = typeof amount === "string" ? Number(amount) : amount;
  const formatted = n.toLocaleString("en-AE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return (
    <span className={`money ${className}`}>
      <span className="text-ink-700 mr-1">{currency}</span>
      {formatted}
    </span>
  );
}
