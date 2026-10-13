local state = require("srs.state")
local render = require("srs.render")

local M = {}

local function send(event)
	if state.proc then
		state.proc:write(vim.json.encode(event) .. "\n")
	end
end

function M.send(type, extra)
	send(vim.tbl_extend("force", { type = type }, extra or {}))
end

local function handle_key(key)
	if state.mode == "rating" then
		local rating = state.buttons[key]
		if rating then
			M.send("rate", { rating = rating })
		end
	elseif state.mode == "question" then
		M.send("reveal", { label = key })
	end
end

local bound = {}

local function bind_keys(keys)
	for key in pairs(bound) do
		pcall(vim.keymap.del, "n", key, { buffer = state.buf })
	end
	bound = {}
	for _, key in ipairs(keys or {}) do
		vim.keymap.set("n", key, function()
			handle_key(key)
		end, { buffer = state.buf })
		bound[key] = true
	end
end

local function handle_message(message)
	if not vim.api.nvim_buf_is_valid(state.buf) then
		return
	end
	local kind = message.type
	if kind == "intro" then
		state.mode = "intro"
		state.due = message.due or 0
		state.card = nil
		render.screen("", table.concat(message.notes or {}, "\n"))
		render.statusline()
	elseif kind == "render" then
		state.mode = message.state
		state.card = message.card or state.card
		state.duration_s = message.duration_s
		if message.state == "question" then
			bind_keys(message.reveal_keys)
		end
		render.note(message)
		render.statusline(message.paused)
	elseif kind == "rating" then
		state.mode = "rating"
		state.buttons = {}
		local keys = {}
		for _, choice in ipairs(message.choices or {}) do
			state.buttons[choice.key] = choice.name
			keys[#keys + 1] = choice.key
		end
		bind_keys(keys)
		state.suggested = type(message.suggested) == "string" and message.suggested or nil
		render.statusline()
	elseif kind == "notice" then
		if message.text ~= "" then
			vim.notify("srs: " .. message.text, message.level == "error" and vim.log.levels.WARN or vim.log.levels.INFO)
		end
	end
end

function M.setup_keymaps(quit)
	local function enter()
		if state.mode == "intro" then
			M.send("start")
		elseif state.mode == "question" then
			M.send("next")
		elseif state.mode == "rating" then
			M.send("rate")
		end
	end
	local function space()
		if state.mode == "question" then
			M.send("pause")
		end
	end
	local function escape()
		if state.mode == "question" then
			M.send("skip")
		end
	end
	vim.keymap.set("n", "<CR>", enter, { buffer = state.buf, desc = "SRS next" })
	vim.keymap.set("n", "<Space>", space, { buffer = state.buf, desc = "SRS pause" })
	vim.keymap.set("n", "<Esc>", escape, { buffer = state.buf, desc = "SRS skip" })
	vim.keymap.set("n", "<C-c>", quit, { buffer = state.buf, desc = "SRS quit" })
end

function M.start(repo_root, python, rpc_path)
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

	state.proc = vim.system({ python, rpc_path }, {
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
			state.restore()
		end)
	end)
end

return M
