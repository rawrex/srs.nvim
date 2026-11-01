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


>[!example] Latex header $\pi + \lambda$, text body
> Foo bar 


>[!example] Text header, latex body
>$\pi + \lambda$


>[!example] Text header, multirow latex body
> Foo bar $\pi^{\dfrac{1}{\sqrt{\lambda^\omega}}}$


>[!example] Multirow latex header, text body $\pi^{\dfrac{1}{\sqrt{\lambda^\omega}}}$
> Body is just text


>[!example] Multirow latex header, multirow latex body $\pi^{\dfrac{1}{\sqrt{\lambda^\omega}}}$
> Foo bar $\pi^{\dfrac{1}{\sqrt{\lambda^\omega}}}$
