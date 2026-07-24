import { redirect } from "next/navigation";

/** design.md §3: "/call" is the primary view — the voice call is the
 * center of the experience, so the app root sends visitors there. */
export default function Home() {
  redirect("/call");
}
