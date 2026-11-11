"""Use the tested passive document hook in the existing signup actor protocol."""
from lab_generate_skill.frozen_account_actor_adapter import FrozenAccountActorAdapter
from lab_generate_skill.signup_document_hooks import SignupDocumentHooks

class FrozenSignupDocumentAdapter(FrozenAccountActorAdapter):
    def NativeReadHooks(self,c,descriptor,directory):
        source=self.verified(c,descriptor)
        return SignupDocumentHooks(self.canonical(c),directory,baseline=source['baseline'])
