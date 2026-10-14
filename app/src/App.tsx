import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import { AccountPage } from "./pages/AccountPage";
import { PaperPage } from "./pages/PaperPage";
import { PapersPage } from "./pages/PapersPage";
import { useAsync } from "./useAsync";

export function App() {
  const meta = useAsync(() => api.meta(), []);
  const wide = useLocation().pathname.startsWith("/paper/");   // trang đọc bài cần rộng cho PDF

  return (
    <>
      <header className="masthead">
        <div className={wide ? "masthead-inner wide" : "masthead-inner"}>
          <Link to="/" className="brand">
            Paper Recommender <small>Gợi ý bài báo khoa học</small>
          </Link>
          <nav className="nav">
            <NavLink to="/" end>Bài báo</NavLink>
            <NavLink to="/account">Tài khoản</NavLink>
          </nav>
        </div>
      </header>

      <main className={wide ? "page wide" : "page"}>
        {meta.error && <p className="error">Không kết nối được tới máy chủ API. {meta.error}</p>}
        <Routes>
          <Route path="/" element={<PapersPage meta={meta.data} />} />
          <Route path="/paper/:id" element={<PaperPage />} />
          <Route path="/account" element={<AccountPage meta={meta.data} />} />
          <Route path="*" element={<p>Không có trang này. <Link to="/">Về trang chủ</Link></p>} />
        </Routes>
      </main>

      <footer className={wide ? "footer wide" : "footer"}>
        Dữ liệu: OpenReview (ICLR, ICML, NeurIPS, TMLR). Bài tập lớn môn Recommender Systems.
      </footer>
    </>
  );
}
