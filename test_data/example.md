- **Hidden** clearly visible **hidden again**, thereby allowing for *different* emphasis

>[!question] Image in the block
>![[image.png]]

>[!example] Code in the block
>```cpp
>int main()
>{
>	std::shared_ptr<Receiver> r;
>	auto cmd = std::make_shared<ConcreteCommand_A>(r, 21);
>	Invoker i{ cmd };
>	{
>       std::unique_lock lock{mtx};
>       i.activated();
>   }
>}
>```

- Latex inline: $n+\pi=\dfrac{1}{\sqrt{\lambda^\omega}}$

>[!example] Latex in the block
> Foo bar $\pi^{\dfrac{1}{\sqrt{\lambda^\omega}}}$
