- *Hidden* clearly visible **hidden again**. Allowing for ***different*** emphasis

>[!question] Image in a block
>![[image.png]]

>[!example] Code in a block
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

>[!example] Text header, latex body
> Foo bar $\pi^{\dfrac{1}{\sqrt{\lambda^\omega}}}$
