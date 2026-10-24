local state = require("srs.state")

local M = {}

local function expand_images(line)
	local media = state.media
	if type(media) ~= "string" or media == "" then
		return line
	end
	return (line:gsub("!%[%[([^%]]+)%]%]", function(reference)
		local filename = vim.fn.fnamemodify((reference:gsub("|.*$", "")), ":t")
		if filename == "" then
			return reference
		end
		return "![](<" .. media .. "/" .. filename .. ">)"
	end))
end

local function set_lines(lines)
	lines = vim.tbl_map(expand_images, lines)
	vim.bo[state.buf].modifiable = true
	vim.api.nvim_buf_set_lines(state.buf, 0, -1, false, lines)
	vim.bo[state.buf].modifiable = false
	vim.api.nvim_win_set_cursor(state.win, { 1, 0 })
end

function M.screen(title, body)
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

function M.statusline(paused)
	if not state.win or not vim.api.nvim_win_is_valid(state.win) then
		return
	end
	local card, intro = state.card, state.mode == "intro"
	local raw = intro and "SRS session" or (card and card.note)
	local note = (raw and raw ~= "") and (raw:gsub("^/", "") .. " ") or ""
	local suffix = paused and " (PAUSED)" or ""
	local hint = (state.suggested and state.suggested ~= "") and (" | " .. state.suggested .. "?") or ""
	local timer = state.duration_s and string.format("| %.1fs", state.duration_s) or ""
	vim.wo[state.win].statusline = string.format(
		"[%d/%d] %s%s%s%s",
		intro and 0 or (card and card.index or 0),
		intro and (state.due or 0) or (card and card.total or 0),
		note,
		suffix,
		timer,
		hint
	)
end

function M.note(message)
	set_note_name(message.card)
	local active, first, text = message.active, nil, ""
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

return M
