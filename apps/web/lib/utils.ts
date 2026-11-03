import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// tailwind-merge has to know the project's own tokens, or it drops e.g. `shadow-page` as a
// conflict it can't classify.
const merge = extendTailwindMerge({
  extend: {
    classGroups: {
      shadow: ["shadow-page"],
      rounded: ["rounded-paper"],
      "font-family": ["font-display", "font-body", "font-script"],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return merge(clsx(inputs));
}
