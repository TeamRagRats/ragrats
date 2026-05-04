import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export default async function RootPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get("ragrats_token");

  if (token) {
    redirect("/chat");
  } else {
    redirect("/login");
  }
}
