export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const ASSET = "https://customer-assets-cm19k8pv.emergentagent.net/job_474b1d61-155f-405a-83f9-494f0b12b9a6/artifacts/";
export const LOGO = `${ASSET}k9an29fp_Logo.png`;
export const api = async (path, options = {}) => {
  const r = await fetch(`${API}${path}`, { credentials: "include", ...options });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Something went wrong");
  return d;
};
export const post = (path, body, method = "POST") => api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const imgUrl = (url) => (url?.startsWith("http") ? url : `${process.env.REACT_APP_BACKEND_URL}${url?.startsWith("/uploads/") ? "/api" + url : url}`);
export const rupee = (n) => `₹${Number(n).toFixed(0)}`;
export const fmtTime = (iso) => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
export const fmtDate = (iso) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
export const ORDER_TYPES = { dine_in: "Dine-in", takeaway: "Takeaway" };
export const STATUSES = ["new", "accepted", "preparing", "ready", "completed", "cancelled"];
export const STATUS_LABEL = { new: "New", accepted: "Accepted", preparing: "Preparing", ready: "Ready", completed: "Completed", cancelled: "Cancelled" };
export const TRACK_STEPS = [
  { key: "new", title: "Order Received", note: "Your story has been written down." },
  { key: "accepted", title: "Accepted", note: "The café has accepted your order." },
  { key: "preparing", title: "Preparing", note: "Brewing, baking and plating with care." },
  { key: "ready", title: "Ready", note: "Your order is ready to be enjoyed." },
  { key: "completed", title: "Completed", note: "Thank you — another chapter shared." },
];
