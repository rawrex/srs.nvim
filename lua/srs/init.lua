local M = {}

local REVEAL_KEYS = "abcdefghijklmnopqrstuvwxyz0123456789"

local state = {
	proc = nil,
	win = nil,
	buf = nil,
	prev_buf = nil,
	quitting = false,
	mode = "idle", -- "intro" | "question" | "rating" | "idle"
	buttons = {},
	suggested = nil,
}

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

-- Environment ---------------------------------------------------------------

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

-- Rendering -----------------------------------------------------------------

local function set_lines(lines)
	vim.bo[state.buf].modifiable = true
	vim.api.nvim_buf_set_lines(state.buf, 0, -1, false, lines)
	vim.bo[state.buf].modifiable = false
	vim.api.nvim_win_set_cursor(state.win, { 1, 0 })
end

local function screen(title, body)
	local lines = {}
	if title ~= "" then
		vim.list_extend(lines, vim.split(title, "\n", { plain = true }))
	end
	if body ~= "" then
		vim.list_extend(lines, vim.split(body, "\n", { plain = true }))
	end
	set_lines(lines)
end

local function set_note_name(card)
	if not card or not card.note or card.note == "" then
		return
	end
	if not pcall(vim.api.nvim_buf_set_name, state.buf, card.note) then
		pcall(vim.api.nvim_buf_set_name, state.buf, vim.fn.fnamemodify(card.note, ":t") .. " [srs]")
	end
end

local function set_statusline(current, total, note, paused)
	if state.win and vim.api.nvim_win_is_valid(state.win) then
		local label = (note and note ~= "") and ((note:gsub("^/", "")) .. " ") or ""
		local suffix = paused and " (PAUSED)" or ""
		vim.wo[state.win].statusline = string.format("[%d/%d] %s%s", current or 0, total or 0, label, suffix)
	end
end

local function render_note(message)
	set_note_name(message.card)
	local active = message.active
	local first, text = nil, ""
	for _, segment in ipairs(message.segments or {}) do
		local chunk = segment.text or ""
		if active and segment.start == active.start and segment["end"] == active["end"] then
			first = select(2, text:gsub("\n", "")) + 1
		end
		text = text .. chunk
	end
	local lines = vim.split(text, "\n", { plain = true })
	if lines[#lines] == "" then
		table.remove(lines)
	end
	set_lines(lines)
	if first then
		vim.api.nvim_win_set_cursor(state.win, { math.min(first, #lines), 0 })
	end
end

-- Events --------------------------------------------------------------------

local function send(event)
	if state.proc then
		state.proc:write(vim.json.encode(event) .. "\n")
	end
end

local function handle_message(message)
	if not vim.api.nvim_buf_is_valid(state.buf) then
		return
	end
	local kind = message.type
	if kind == "intro" then
		state.mode = "intro"
		set_statusline(0, message.due or 0, "SRS session")
		screen("", table.concat(message.notes or {}, "\n"))
	elseif kind == "render" then
		state.mode = message.state
		if message.card then
			set_statusline(message.card.index or 0, message.card.total or 0, message.card.note, message.paused)
		end
		render_note(message)
	elseif kind == "rating" then
		state.mode = "rating"
		state.buttons = {}
		for _, choice in ipairs(message.choices or {}) do
			state.buttons[choice.name] = choice.key
		end
		state.suggested = type(message.suggested) == "string" and message.suggested or nil
	elseif kind == "notice" then
		if message.text ~= "" then
			vim.notify("srs: " .. message.text, message.level == "error" and vim.log.levels.WARN or vim.log.levels.INFO)
		end
	end
end

local function handle_key(key)
	if state.mode == "rating" then
		for name, char in pairs(state.buttons) do
			if char == key then
				send({ type = "rate", rating = name })
				return
			end
		end
	elseif state.mode == "question" then
		send({ type = "reveal", label = key })
	end
end

-- Session -------------------------------------------------------------------

local function setup_keymaps()
	vim.keymap.set("n", "<CR>", function()
		if state.mode == "intro" then
			send({ type = "start" })
		elseif state.mode == "question" then
			send({ type = "next" })
		elseif state.mode == "rating" then
			send({ type = "rate" })
		end
	end, { buffer = state.buf, desc = "SRS next" })

	vim.keymap.set("n", "<Space>", function()
		if state.mode == "question" then
			send({ type = "pause" })
		end
	end, { buffer = state.buf, desc = "SRS pause" })

	vim.keymap.set("n", "<Esc>", function()
		if state.mode == "question" then
			send({ type = "skip" })
		end
	end, { buffer = state.buf, desc = "SRS skip" })

	vim.keymap.set("n", "<C-c>", M.close, { buffer = state.buf, desc = "SRS quit" })

	for key in REVEAL_KEYS:gmatch(".") do
		vim.keymap.set("n", key, function()
			handle_key(key)
		end, { buffer = state.buf })
	end
end

local function restore()
	if
		state.win
		and vim.api.nvim_win_is_valid(state.win)
		and state.prev_buf
		and vim.api.nvim_buf_is_valid(state.prev_buf)
	then
		vim.api.nvim_win_set_buf(state.win, state.prev_buf)
	end
	state.mode = "idle"
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

	state.prev_buf = vim.api.nvim_get_current_buf()
	state.win = vim.api.nvim_get_current_win()
	state.buf = vim.api.nvim_create_buf(false, true)
	vim.bo[state.buf].filetype = "markdown"
	vim.bo[state.buf].bufhidden = "wipe"
	vim.api.nvim_win_set_buf(state.win, state.buf)
	state.quitting = false
	setup_keymaps()

	local buffered = ""
	local function on_stdout(_, data)
		buffered = buffered .. (data or "")
		while true do
			local newline = buffered:find("\n", 1, true)
			if not newline then
				break
			end
			local line = buffered:sub(1, newline - 1)
			buffered = buffered:sub(newline + 1)
			if line ~= "" then
				local ok, message = pcall(vim.json.decode, line)
				if ok then
					vim.schedule(function()
						handle_message(message)
					end)
				end
			end
		end
	end

	state.proc = vim.system({ python(), plugin_root() .. "/core/rpc.py" }, {
		cwd = repo_root,
		stdin = true,
		stdout = on_stdout,
		stderr = function(_, data)
			if data and data ~= "" then
				vim.schedule(function()
					vim.notify("srs: " .. vim.trim(data), vim.log.levels.WARN)
				end)
			end
		end,
		text = true,
	}, function(completed)
		vim.schedule(function()
			state.proc = nil
			if state.quitting then
				return
			end
			if completed.code ~= 0 then
				vim.notify("srs: process exited with code " .. tostring(completed.code), vim.log.levels.ERROR)
			end
			restore()
		end)
	end)
end

function M.close()
	state.quitting = true
	if state.proc then
		state.proc:kill(15)
		state.proc = nil
	end
	restore()
end

return M
