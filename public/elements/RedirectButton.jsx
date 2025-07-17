import { Button } from "@/components/ui/button";
import { ExternalLink } from "lucide-react";

export default function RedirectButton() {
  const handleRedirect = () => {
    const redirectUrl = `${props.url}?email=${encodeURIComponent(props.email)}`;
    window.location.href = redirectUrl;
  };

  return (
    <div className="flex justify-start w-full">
      <Button 
        className="inline-flex items-center gap-2 w-auto"
        variant={props.variant || "default"} 
        onClick={handleRedirect}
      >
        {props.buttonText}
        <ExternalLink size={16} />
      </Button>
    </div>
  );
}
