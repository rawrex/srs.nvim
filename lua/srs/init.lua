local state = require("srs.state")
local client = require("srs.client")

local M = {}

function M.setup(opts)
	M.config = opts or {}
	if vim.g.loaded_srs_nvim ~= 1 then
		vim.g.loaded_srs_nvim = 1
		vim.api.nvim_create_user_command("SrsReview", function()
			M.review()
		end, { desc = "Start an SRS review session" })
	end
	return M
end

local function plugin_root()
	return vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h:h")
end

local function python()
	local venv = vim.env.VIRTUAL_ENV
	if venv and venv ~= "" and vim.fn.executable(venv .. "/bin/python") == 1 then
		return venv .. "/bin/python"
	end
	return "python3"
end

function M.review()
	if state.proc then
		vim.notify("srs: review already running", vim.log.levels.WARN)
		return
	end

	local repo_root = vim.fs.root(0, { ".git", ".srs" })
	if not repo_root then
		vim.notify("srs: not inside a git repository", vim.log.levels.ERROR)
		return
	end

	state.reset()
	state.prev_buf = vim.api.nvim_get_current_buf()
	state.win = vim.api.nvim_get_current_win()
	state.buf = vim.api.nvim_create_buf(false, true)
	vim.bo[state.buf].filetype = "markdown"
	vim.bo[state.buf].bufhidden = "wipe"
	vim.api.nvim_win_set_buf(state.win, state.buf)
	state.quitting = false
	client.setup_keymaps(M.close)
	client.start(repo_root, python(), plugin_root() .. "/core/rpc.py")
end

function M.close()
	state.quitting = true
	if state.proc then
		state.proc:kill(15)
		state.proc = nil
	end
	state.restore()
end

return M
