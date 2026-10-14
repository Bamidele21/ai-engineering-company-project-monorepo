export default function SiteFooter() {
  return (
    <footer className="mt-10 w-full border-t border-orange-300/40 bg-gradient-to-r from-rose-500 to-orange-500 py-6 text-orange-50">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-center justify-between px-4 text-center sm:px-6 md:flex-row md:text-left">
        <span className="text-sm sm:text-base">© 2025 Nexova. All rights reserved.</span>
        <div className="mt-4 flex space-x-6 text-amber-100 md:mt-0">
          <a
            href="https://linkedin.com/company/nexova"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-white"
          >
            LinkedIn
          </a>
          <a
            href="https://instagram.com/nexova"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-white"
          >
            Instagram
          </a>
        </div>
      </div>
    </footer>
  );
}
