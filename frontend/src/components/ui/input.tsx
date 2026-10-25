import * as React from "react"
import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "border-input bg-background text-foreground placeholder:text-muted-foreground flex h-9 w-full min-w-0 rounded-lg border px-3 py-1 text-[13px] shadow-2xs transition-colors outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/25 hover:border-brand-300 dark:hover:border-brand-700 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}

export { Input }
