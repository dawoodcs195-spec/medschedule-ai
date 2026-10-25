import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-[background-color,border-color,color,box-shadow,transform,filter] duration-200 ease-out cursor-pointer outline-none select-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-xs hover:bg-primary/90 hover:shadow-md hover:shadow-primary/20",
        destructive:
          "bg-rose-50 text-rose-700 border border-rose-200/90 hover:bg-rose-100/90 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800/80 dark:hover:bg-rose-900/50",
        outline:
          "border border-border bg-card text-foreground shadow-2xs hover:border-brand-300 hover:bg-brand-50/60 hover:text-foreground dark:hover:border-brand-700 dark:hover:bg-brand-950/40",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "text-muted-foreground hover:bg-muted hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
        brand:
          "bg-linear-to-b from-brand-600 to-brand-700 text-white shadow-sm shadow-brand-900/20 ring-1 ring-inset ring-white/15 hover:brightness-110 hover:shadow-md hover:shadow-brand-700/30 dark:from-brand-400 dark:to-brand-500 dark:text-brand-950",
        soft:
          "bg-brand-50/90 text-brand-800 border border-brand-200/80 hover:bg-brand-100/80 dark:bg-brand-950/50 dark:text-brand-200 dark:border-brand-800/70 dark:hover:bg-brand-900/50",
        amber:
          "bg-amber-50/90 text-amber-800 border border-amber-200/90 hover:bg-amber-100/80 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800/70",
        emerald:
          "bg-emerald-50/90 text-emerald-800 border border-emerald-200/90 hover:bg-emerald-100/80 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800/70",
      },
      size: {
        default: "h-9 px-3.5 py-1.5",
        xs: "h-7 px-2.5 text-[11px] rounded-md",
        sm: "h-8 px-3 text-xs rounded-lg",
        lg: "h-10 px-4.5 text-sm font-semibold rounded-xl",
        xl: "h-12 px-6 text-sm sm:text-base font-semibold rounded-xl",
        icon: "size-8 rounded-lg",
        "icon-sm": "size-7 rounded-md",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = "button", ...props }, ref) => {
    return (
      <button
        type={type}
        ref={ref}
        data-slot="button"
        className={cn(buttonVariants({ variant, size, className }))}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
